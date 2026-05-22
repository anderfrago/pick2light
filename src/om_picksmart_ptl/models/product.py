import requests
import json
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    tag_mac = fields.Char(string="Tag MAC Address")
    pickup_quantity = fields.Float(string="Pickup Quantity", default=0.0)

    def write(self, vals):
        # 1. Ejecutamos el guardado estándar en PostgreSQL primero
        res = super(ProductTemplate, self).write(vals)
        
        # 2. Si el cambio viene provocado por el propio botón del hardware, 
        # salimos inmediatamente para evitar bucles infinitos de red HTTP.
        if self.env.context.get('is_picksmart_callback'):
            return res

        # 3. Campos que deben disparar la actualización de la pantalla de tinta electrónica:
        # Añadimos 'qty_available' para capturar los ajustes manuales directos en ficha.
        fields_to_sync = ['tag_mac', 'name', 'pickup_quantity', 'qty_available']
        
        for record in self:
            # Comprobamos si el producto tiene un tag asociado
            if record.tag_mac:
                # Caso A: Se modificó un campo directo de la ficha (Nombre, Mac, Pick)
                changed_direct_field = any(f in vals for f in fields_to_sync)
                
                # Caso B: El stock ha cambiado (comparamos el valor real recalculado)
                # Odoo a veces no mete 'qty_available' en vals porque es un computed, 
                # así que forzamos una validación de contexto si viene de un ajuste.
                is_inventory_adjustment = self.env.context.get('inventory_mode') or 'inventory_quantity' in vals

                if changed_direct_field or is_inventory_adjustment:
                    try:
                        _logger.error("!!! ODOO INTERFAZ -> Cambio manual detectado en %s (Stock o Datos). Sincronizando hardware...", record.name)
                        
                        # Destruimos cachés para asegurar que el método lea el número neto real recién guardado
                        record.invalidate_recordset(['qty_available'])
                        
                        # Enviamos la actualización física al Router
                        record._update_picksmart_tag(led_rgb="00ff00" if record.pickup_quantity > 0 else "000000")
                    except Exception as e:
                        _logger.error("!!! ODOO INTERFAZ -> Fallo al transmitir cambio manual: %s", str(e))
        return res
    
    def _update_picksmart_tag(self, led_rgb=None):
        """
        Envía la trama de actualización de pantalla y LED al Router Picksmart.
        Configura el outtime en '0' para que la luz NO se apague nunca por tiempo.
        """
        self.ensure_one()
        params = self.env['ir.config_parameter'].sudo()
        router_ip = params.get_param('picksmart.router_ip') or '192.168.1.200'
        style_id = params.get_param('picksmart.style_id') or '50'
                
        # 1. LOGICA DE COLORES AUTOMÁTICA SEGÚN EL FLUJO:
        # Si no nos pasan un color explícito, miramos el signo del picking:
        if not led_rgb:
            if self.pickup_quantity < 0:
                led_rgb = "0000ff"  # Azul -> Recepción / Entrada
            elif self.pickup_quantity > 0:
                led_rgb = "00ff00"  # Verde -> Entrega / Salida
            else:
                led_rgb = "000000"  # Sin luz -> El picking está a cero

        # Determinamos el estado del LED (00: Apagado, 01: Parpadeo)
        led_state = "01" if led_rgb != "000000" else "00"

        # 2. CONSTRUCCIÓN DEL PAYLOAD PARA EL ROUTER
        payload = [{
            "mac": str(self.tag_mac).replace('CWT', '').strip(),
            "styleid": str(style_id),
            "mappingtype": "791",
            "productName": str(self.name or ''),
            "Stock": str(int(self.qty_available or 0)),
            "basketsQuantity": str(int(self.pickup_quantity or 0)),
            "ledstate": led_state,
            "ledrgb": str(led_rgb),
            # -------------------------------------------------------------------------
            # CAMBIO CRÍTICO: '0' significa tiempo infinito. 
            # El LED parpadeará constantemente hasta que el hardware reciba otra orden.
            # -------------------------------------------------------------------------
            "outtime": "0", 
            "arrow": ""
        }]

        url = f"http://{router_ip}/wms/associate/updateScreen"
        headers = {'Content-Type': 'application/json'}
        try:
            requests.post(url, json=payload, headers=headers, timeout=5)
            _logger.error("!!! HARDWARE TAG -> Comando enviado con éxito. LED Permanente: %s", led_rgb)
        except Exception as e:
            _logger.error("!!! CONTROLADOR ROUTER -> Error de envío HTTP: %s", str(e))

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def action_apply_inventory(self):
        # 1. Aplicamos el ajuste de inventario nativo de Odoo
        res = super(StockQuant, self).action_apply_inventory()
        
        # 2. Recorremos los productos afectados y mandamos la señal al hardware
        for quant in self:
            product_tmpl = quant.product_id.product_tmpl_id
            if product_tmpl.tag_mac and not self.env.context.get('is_picksmart_callback'):
                _logger.error("!!! STOCK QUANT -> Ajuste de inventario manual aplicado para: %s. Sincronizando tag.", product_tmpl.name)
                product_tmpl.invalidate_recordset(['qty_available'])
                product_tmpl._update_picksmart_tag(led_rgb="00ff00" if product_tmpl.pickup_quantity > 0 else "000000")
        return res