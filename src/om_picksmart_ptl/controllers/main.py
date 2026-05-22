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

                # 1. Limpiamos la caché de Odoo en la Raspberry para leer datos frescos de Postgres
                product.invalidate_recordset(['pickup_quantity', 'qty_available'])
                
                # -------------------------------------------------------------------------
                # ¡LA CLAVE DE LA ARITMÉTICA!: Capturamos el valor original con su SIGNO real
                # Si en Odoo el picking está en -5.0 (Recepción), sign_value será -5.0.
                # Si en Odoo el picking está en 5.0 (Entrega), sign_value será 5.0.
                # -------------------------------------------------------------------------
                sign_value = product.pickup_quantity
                _logger.error("!!! Botón 0 -> Valor original guardado en el picking de Odoo: %s", sign_value)

                # 2. Buscamos el albarán activo (sea entrante o saliente)
                move = request.env['stock.move'].sudo().search([
                    ('product_id', 'in', product.product_variant_ids.ids),
                    ('state', 'in', ['confirmed', 'assigned', 'partially_available'])
                ], order='create_date asc', limit=1)
                
                # Definimos la cantidad absoluta (siempre positiva) para las líneas de movimiento de Odoo
                qty_to_process = move.product_uom_qty if move else abs(sign_value)
                _logger.error("!!! Botón 0 -> Cantidad neta para el documento de Odoo: %s", qty_to_process)

                # 3. Ponemos el picking a 0 en Odoo para liberar la pantalla física
                product_ctx.write({'pickup_quantity': 0.0})
                request.env.cr.commit() 
                
                # Determinar si es una salida (Entrega) basándonos en el signo original del picking
                # Si era positivo (> 0), es una salida. Si era negativo (< 0), es una entrada.
                is_outgoing = (sign_value > 0)

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
                        
                        # VALIDACIÓN FINAL DE ODOO (Nativa: Suma entradas / Resta salidas)
                        _logger.error("!!! Botón 0 -> Ejecutando button_validate() para %s", picking.name)
                        picking.with_context(is_picksmart_callback=True).button_validate()
                        
                        # Forzamos la limpieza de caché total para asimilar el cambio nativo
                        request.env.invalidate_all()
                        
                        # LLAMADA FORZADA SEGURA:
                        # Mandamos a regularizar el stock indicándole explícitamente si fue una salida o entrada.
                        # Pasamos is_albaran=False para que _adjust_stock aplique la matemática exacta por si Odoo 
                        # tarda en hacer el commit en este hilo.
                        self._adjust_stock(product, qty_to_process, is_albaran=False, is_outgoing=is_outgoing)

                    except Exception as e:
                        _logger.error("!!! Error crítico validando albarán hardware, aplicando salvavidas manual: %s", str(e))
                        picking.write({'state': 'done'})
                        move.write({'state': 'done'})
                        request.env.cr.commit()
                        
                        if qty_to_process > 0:
                            self._adjust_stock(product, qty_to_process, is_albaran=False, is_outgoing=is_outgoing)
                else:
                    # MODO MANUAL PURO (Pulsaciones libres en almacén)
                    if qty_to_process > 0:
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