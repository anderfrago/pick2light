from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class PicksmartController(http.Controller):

    @http.route('/picksmart/callback', type='http', auth='public', methods=['POST'], csrf=False)
    def tag_callback(self, **post):
        try:
            data = json.loads(request.httprequest.data)
            _logger.error("!!! REGISTRO DE SEÑAL HARDWARE RECIBIDA: %s", data)
            
            mac = str(data.get('mac', '')).replace('CWT', '').strip()
            button_id = data.get('result') if data.get('result') is not None else data.get('buttonId')

            product = request.env['product.template'].sudo().search([
                ('tag_mac', '=', mac)
            ], limit=1)
            
            if not product:
                _logger.error("!!! TAG NO ENCONTRADO PARA LA MAC: %s", mac)
                return request.make_response(json.dumps({"status": "error"}), headers={'Content-Type': 'application/json'})

            if button_id == 0:
                # 1. RESPALDAMOS EL VALOR REAL DEL PICKING ANTES DE BORRARLO
                # Necesitamos saber cuántas unidades reflejaba la pantalla del hardware.
                baskets_to_clear = product.pickup_quantity
                _logger.error("!!! Botón 0: Cantidad en pantalla a procesar: %s", baskets_to_clear)

                # 2. MULTI-WORKER SHIELD: Activamos el candado e inicializamos el valor visual
                product.write({
                    'is_hardware_updating': True,
                    'pickup_quantity': 0.0
                })
                request.env.cr.commit() 

                move = request.env['stock.move'].sudo().search([
                    ('product_id', 'in', product.product_variant_ids.ids),
                    ('state', 'in', ['confirmed', 'assigned', 'partially_available'])
                ], order='create_date asc', limit=1)
                
                if move:
                    picking = move.picking_id
                    _logger.error("!!! Botón 0: Procesando movimiento %s para el Albarán %s", move.id, picking.name)
                    
                    try:
                        # Forzamos que las líneas de Odoo tengan la cantidad exacta del movimiento
                        if not move.move_line_ids:
                            request.env['stock.move.line'].sudo().create({
                                'move_id': move.id,
                                'picking_id': picking.id,
                                'product_id': move.product_id.id,
                                'product_uom_id': move.product_uom.id,
                                'location_id': move.location_id.id,
                                'location_dest_id': move.location_dest_id.id,
                                'quantity': move.product_uom_qty,
                            })
                        else:
                            for line in move.move_line_ids:
                                line.quantity = move.product_uom_qty
                        
                        # Guardamos el stock antes de la validación nativa para verificar si Odoo realmente restó
                        stock_antes = product.qty_available
                        
                        # Validación nativa de Odoo
                        move._action_done()
                        
                        # Comprobamos si quedan movimientos en el albarán
                        remaining_moves = picking.move_ids.filtered(lambda m: m.state not in ['done', 'cancel'])
                        if not remaining_moves:
                            picking.write({'state': 'done'})
                        
                        # Forzamos recálculo en este hilo para comprobar el efecto de Odoo
                        product.invalidate_recordset(['qty_available'])
                        
                        # =========================================================================
                        # CONTROL DE SEGURIDAD POST-VALIDACIÓN:
                        # Si Odoo hizo el '_action_done()' pero el stock a la mano NO se redujo 
                        # (por culpa de ubicaciones virtuales o almacenes cruzados), aplicamos la resta manual.
                        # =========================================================================
                        if product.qty_available >= stock_antes and baskets_to_clear > 0:
                            _logger.error("!!! Alerta: Odoo no aplicó la resta física en las tablas de inventario. Forzando ajuste de -%s", baskets_to_clear)
                            self._adjust_stock(product, -baskets_to_clear)
                        else:
                            _logger.error("!!! Botón 0: Odoo restó el stock correctamente por vía nativa.")
                        
                    except Exception as validation_error:
                        _logger.error("!!! Error en validación nativa: %s. Aplicando bypass y ajuste físico.", str(validation_error))
                        # Si Odoo da un error duro (Falta de stock, etc.), forzamos estados lógicos y restamos a mano
                        move.write({'state': 'done'})
                        if not picking.move_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
                            picking.write({'state': 'done'})
                        
                        if baskets_to_clear > 0:
                            self._adjust_stock(product, -baskets_to_clear)
                
                else:
                    # CASO SIN MOVIMIENTOS LOGÍSTICOS PENDIENTES
                    if baskets_to_clear > 0:
                        _logger.error("!!! Botón 0 sin albaranes: Aplicando ajuste de stock manual. Restando %s", baskets_to_clear)
                        self._adjust_stock(product, -baskets_to_clear)
                    else:
                        _logger.error("!!! Botón 0 presionado sin albaranes ni cantidades pendientes.")

            elif button_id == 1:
                self._adjust_stock(product, 1.0)

            elif button_id == 3:
                self._adjust_stock(product, 3.0)

            # -------------------------------------------------------------------------
            # LIBERAMOS EL CANDADO Y ENVIAMOS AL HARDWARE
            # -------------------------------------------------------------------------
            product.write({
                'is_hardware_updating': False,
                'pickup_quantity': 0.0 if button_id == 0 else product.pickup_quantity
            })
            request.env.cr.commit()
            
            product.invalidate_recordset(['qty_available', 'pickup_quantity', 'is_hardware_updating'])
            
            _logger.error("!!! ENVIANDO ACTUALIZACIÓN AL HARDWARE -> MAC: %s | STOCK: %s | PICKING: %s", 
                         product.tag_mac, product.qty_available, product.pickup_quantity)
            product._update_picksmart_tag(led_rgb="000000" if button_id == 0 else "00ff00")

            return request.make_response(json.dumps({"status": "success"}), headers={'Content-Type': 'application/json'})
            
        except Exception as e:
            try:
                product.write({'is_hardware_updating': False})
                request.env.cr.commit()
            except:
                pass
            request.env.cr.rollback()
            _logger.error("!!! CRASH EN CALLBACK CONTROLLER: %s", str(e))
            return request.make_response(json.dumps({"status": "error", "message": str(e)}), headers={'Content-Type': 'application/json'})

    def _adjust_stock(self, product, amount):
        location = request.env['stock.location'].sudo().search([('usage', '=', 'internal')], limit=1)
        product_variant = product.product_variant_id
        current_stock = product.qty_available
        new_stock = current_stock + amount

        quant = request.env['stock.quant'].sudo().with_context(inventory_mode=True).search([
            ('product_id', '=', product_variant.id),
            ('location_id', '=', location.id)
        ], limit=1)

        if quant:
            quant.inventory_quantity = new_stock
            quant.action_apply_inventory()
        else:
            request.env['stock.quant'].sudo().with_context(inventory_mode=True).create({
                'product_id': product_variant.id,
                'location_id': location.id,
                'inventory_quantity': new_stock,
            }).action_apply_inventory()