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
            _logger.error("!!! HARDWARE -> SEÑAL RECIBIDA: %s", data)
            
            mac = str(data.get('mac', '')).replace('CWT', '').strip()
            button_id = data.get('result') if data.get('result') is not None else data.get('buttonId')

            # Buscamos el producto
            product = request.env['product.template'].sudo().search([
                ('tag_mac', '=', mac)
            ], limit=1)
            
            if not product:
                _logger.error("!!! HARDWARE -> MAC NO ENCONTRADA: %s", mac)
                return request.make_response(json.dumps({"status": "error"}), headers={'Content-Type': 'application/json'})

            # Creamos un entorno con un contexto especial para avisar a Odoo que esta acción viene del hardware
            product_ctx = product.with_context(is_picksmart_callback=True)
  
            if button_id == 0:
                _logger.error("!!! Botón 0 -> Solicitud de confirmación de operación recibida.")

                # 1. Limpiamos la caché de Odoo en la Raspberry para leer datos frescos
                product.invalidate_recordset(['pickup_quantity', 'qty_available'])
                
                # 2. Buscamos el albarán activo (sea entrante o saliente)
                move = request.env['stock.move'].sudo().search([
                    ('product_id', 'in', product.product_variant_ids.ids),
                    ('state', 'in', ['confirmed', 'assigned', 'partially_available'])
                ], order='create_date asc', limit=1)
                
                # 3. Extraemos el valor real neto del documento de Odoo
                qty_to_process = move.product_uom_qty if move else abs(product.pickup_quantity)
                _logger.error("!!! Botón 0 -> Procesando cantidad real neta del documento: %s", qty_to_process)

                # 4. Ponemos el picking a 0 en Odoo para liberar la pantalla
                product_ctx.write({'pickup_quantity': 0.0})
                request.env.cr.commit() 
                
                if move:
                    picking = move.picking_id
                    try:
                        # Aseguramos que existan las líneas físicas del albarán (move lines)
                        if not move.move_line_ids:
                            request.env['stock.move.line'].sudo().create({
                                'move_id': move.id,
                                'picking_id': picking.id,
                                'product_id': move.product_id.id,
                                'product_uom_id': move.product_uom.id,
                                'location_id': move.location_id.id,
                                'location_dest_id': move.location_dest_id.id,
                                'quantity': qty_to_process,
                            })
                        else:
                            for line in move.move_line_ids:
                                line.quantity = qty_to_process
                        
                        # VALIDACIÓN FINAL DE ODOO (Suma si es entrada / Resta si es salida de forma nativa)
                        _logger.error("!!! Botón 0 -> Ejecutando button_validate() para %s", picking.name)
                        picking.with_context(is_picksmart_callback=True).button_validate()
                        
                        # Llamamos a tu función con '0' para que Odoo refresque la pantalla con la nueva realidad contable
                        self._adjust_stock(product, 0)

                    except Exception as e:
                        _logger.error("!!! Error crítico validando albarán hardware, aplicando salvavidas: %s", str(e))
                        picking.write({'state': 'done'})
                        move.write({'state': 'done'})
                        
                        # Si es una emergencia y Odoo crashea, tu función inteligente _adjust_stock se encargará del resto
                        if qty_to_process > 0:
                            self._adjust_stock(product, qty_to_process)
                else:
                    # MODO MANUAL PURO (Pulsaciones libres en almacén)
                    if qty_to_process > 0:
                        self._adjust_stock(product, qty_to_process)
            elif button_id == 1:
                _logger.error("!!! Hardware -> Modificando stock en +1.0")
                self._adjust_stock(product, 1.0)

            elif button_id == 3:
                _logger.error("!!! Hardware -> Modificando stock en +3.0")
                self._adjust_stock(product, 3.0)

            # -------------------------------------------------------------------------
            # FORZAR RECALCULO TOTAL EVITANDO CACHÉS DE RAM
            # -------------------------------------------------------------------------
            request.env.invalidate_all() # Limpia por completo la caché intermedia de Odoo
            
            _logger.error("!!! HARDWARE -> TRANSMITIENDO VALORES ACTUALIZADOS: MAC %s | STOCK REAL %s | PICK %s", 
                         product.tag_mac, product.qty_available, product.pickup_quantity)
            
            # Forzamos el envío físico de la pantalla
            product._update_picksmart_tag(led_rgb="000000" if button_id == 0 else "00ff00")

            return request.make_response(json.dumps({"status": "success"}), headers={'Content-Type': 'application/json'})
            
        except Exception as e:
            request.env.cr.rollback()
            _logger.error("!!! CRASH EN CONTROLADOR GENERAL: %s", str(e))
            return request.make_response(json.dumps({"status": "error"}), headers={'Content-Type': 'application/json'})

    def _adjust_stock(self, product, amount):
        location = request.env['stock.location'].sudo().search([('usage', '=', 'internal')], limit=1)
        product_variant = product.product_variant_id
        
        request.env.invalidate_all()
        current_stock = product_variant.qty_available

        # -------------------------------------------------------------------------
        # FILTRO INTELIGENTE DE MODOS:
        # Buscamos si hay un albarán de entrada activo en este preciso momento.
        # -------------------------------------------------------------------------
        move = request.env['stock.move'].sudo().search([
            ('product_id', '=', product_variant.id),
            ('state', 'in', ['confirmed', 'assigned', 'partially_available'])
        ], limit=1)

        if move and amount == 0:
            # MODO ALBARÁN (ÉXITO): El Botón 0 ya procesó el stock nativamente.
            # Nos comportamos como tu código corregido: Solo leemos y refrescamos.
            new_stock = current_stock
        else:
            # MODO MANUAL (Botones 1 y 3) o AJUSTE FORZADO:
            # Sumamos el incremento directo (+1.0 o +3.0) que viene del hardware.
            new_stock = current_stock + amount

        _logger.error("!!! INTERFAZ HARDWARE -> %s | Stock base: %s | Ajuste aplicado: %s | Resultado final: %s", 
                     product_variant.display_name, current_stock, amount, new_stock)

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