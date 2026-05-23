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
                _logger.error("!!! Botón 0 -> Solicitud de confirmación de operación recibida (Simple/Lote).")

                # 1. Rompemos las cachés para leer el consolidado real guardado en Postgres
                product.invalidate_recordset(['pickup_quantity', 'qty_available'])
                
                # Capturamos el valor original calculado (sea de albarán único o de suma de lotes)
                sign_value = product.pickup_quantity
                if sign_value == 0.0:
                    _logger.error("!!! Botón 0 -> El picking ya vale 0. Nada que procesar.")
                    return request.make_response(json.dumps({"status": "success"}), headers={'Content-Type': 'application/json'})

                qty_to_process = abs(sign_value)
                is_outgoing = (sign_value > 0)

                _logger.error("!!! Botón 0 -> Procesando cantidad agrupada total: %s | ¿Es salida?: %s", qty_to_process, is_outgoing)

                # 2. Ponemos el picking a 0 en Odoo inmediatamente para liberar el hardware
                product_ctx.write({'pickup_quantity': 0.0})
                request.env.cr.commit() 

                # 3. Buscamos TODOS los movimientos pendientes en lote u individuales de este producto
                moves = request.env['stock.move'].sudo().search([
                    ('product_id', 'in', product.product_variant_ids.ids),
                    ('state', 'in', ['confirmed', 'assigned', 'partially_available'])
                ], order='create_date asc')

                if moves:
                    # Agrupamos los pickings padres afectados para validarlos al final
                    pickings_to_validate = moves.mapped('picking_id')
                    batches_to_validate = pickings_to_validate.mapped('batch_id')

                    try:
                        # Aseguramos cantidades en todas las líneas de movimiento abiertas
                        for move in moves:
                            if not move.move_line_ids:
                                request.env['stock.move.line'].sudo().create({
                                    'move_id': move.id,
                                    'picking_id': move.picking_id.id,
                                    'product_id': move.product_id.id,
                                    'product_uom_id': move.product_uom.id,
                                    'location_id': move.location_id.id,
                                    'location_dest_id': move.location_dest_id.id,
                                    'quantity': move.product_uom_qty,
                                })
                            else:
                                for line in move.move_line_ids:
                                    line.quantity = move.product_uom_qty

                        # VALIDACIÓN EN CASCADA: 
                        # Si los albaranes pertenecen a lotes/olas, validamos el lote contenedor padre.
                        if batches_to_validate:
                            for batch in batches_to_validate:
                                _logger.error("!!! Botón 0 -> Validando Lote/Ola contenedor nativo: %s", batch.name)
                                batch.with_context(is_picksmart_callback=True).action_done()
                        else:
                            # Si eran albaranes simples libres independientes
                            for picking in pickings_to_validate:
                                _logger.error("!!! Botón 0 -> Validando Albarán individual nativo: %s", picking.name)
                                picking.with_context(is_picksmart_callback=True).button_validate()

                        # Forzamos relectura limpia y sincronizamos el stock
                        request.env.invalidate_all()
                        self._adjust_stock(product, qty_to_process, is_albaran=True, is_outgoing=is_outgoing)

                    except Exception as e:
                        _logger.error("!!! Error validando flujo agrupado, aplicando salvavidas matemático: %s", str(e))
                        # Forzamos cierre de estados por seguridad
                        moves.write({'state': 'done'})
                        pickings_to_validate.write({'state': 'done'})
                        if batches_to_validate:
                            batches_to_validate.write({'state': 'done'})
                        request.env.cr.commit()

                        # El salvavidas inyecta la cantidad consolidada exacta con el signo correspondiente
                        self._adjust_stock(product, qty_to_process, is_albaran=False, is_outgoing=is_outgoing)
                else:
                    # MODO MANUAL PURO
                    self._adjust_stock(product, qty_to_process, is_albaran=False, is_outgoing=is_outgoing)
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

    def _adjust_stock(self, product, amount, is_albaran=False, is_outgoing=False):
        """
        Controlador maestro de existencias físicas en Postgres.
        Garantiza matemáticamente la suma en recepciones y la resta en entregas.
        """
        location = request.env['stock.location'].sudo().search([('usage', '=', 'internal')], limit=1)
        product_variant = product.product_variant_id
        
        # Forzamos a Odoo a destruir cualquier dato viejo en la caché RAM de este hilo
        request.env.invalidate_all()
        current_stock = product_variant.qty_available

        if is_albaran:
            # -------------------------------------------------------------------------
            # MODO ALBARÁN EXITOSO:
            # Como Odoo ya ejecutó picking.button_validate() de forma nativa por detrás,
            # el stock real ya ha cambiado en Postgres (Odoo suma o resta solo en las tablas).
            # Nos limitamos a leer la nueva realidad contable sin aplicar matemáticas manuales.
            # -------------------------------------------------------------------------
            new_stock = current_stock
            _logger.error("!!! REFRESCO ALBARÁN -> Stock leído tras validación nativa de Odoo: %s", current_stock)
        else:
            # -------------------------------------------------------------------------
            # MODO MANUAL (Botones 1 y 3) O SALVAVIDAS POR ERROR DE VALIDACIÓN:
            # Forzamos la dirección aritmética de forma estricta según las banderas pasadas.
            # -------------------------------------------------------------------------
            if is_outgoing:
                new_stock = current_stock - amount  # RESTA EN ENTREGAS (Salidas)
                _logger.error("!!! CÁLCULO ARITMÉTICO SALIDA -> Stock actual: %s - Ajuste: %s = Resultado: %s", current_stock, amount, new_stock)
            else:
                new_stock = current_stock + amount  # SUMA EN RECEPCIONES (Entradas)
                _logger.error("!!! CÁLCULO ARITMÉTICO ENTRADA -> Stock actual: %s + Ajuste: %s = Resultado: %s", current_stock, amount, new_stock)

        _logger.error("!!! INYECTANDO A POSTGRES -> %s | Stock Final a escribir: %s", product_variant.display_name, new_stock)

        # Buscamos o creamos el Quant físico para aplicar el cambio definitivo en el inventario
        quant = request.env['stock.quant'].sudo().with_context(is_picksmart_callback=True).search([
            ('product_id', '=', product_variant.id),
            ('location_id', '=', location.id)
        ], limit=1)

        if quant:
            quant.with_context(inventory_mode=True).inventory_quantity = new_stock
            quant.with_context(is_picksmart_callback=True).action_apply_inventory()
        else:
            request.env['stock.quant'].sudo().with_context(inventory_mode=True).create({
                'product_id': product_variant.id,
                'location_id': location.id,
                'inventory_quantity': new_stock,
            }).with_context(is_picksmart_callback=True).action_apply_inventory()