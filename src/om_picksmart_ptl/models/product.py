import requests
import json
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    tag_mac = fields.Char(string="Tag MAC Address")
    pickup_quantity = fields.Float(string="Pickup Quantity", default=0.0)
    is_hardware_updating = fields.Boolean(string="Hardware lock", default=False)

    def write(self, vals):
        # Si el candado está puesto en base de datos, guardamos los valores pero no disparamos llamadas HTTP externas
        for record in self:
            if record.is_hardware_updating:
                return super(ProductTemplate, self).write(vals)

        res = super(ProductTemplate, self).write(vals)
        if self.env.context.get('is_picksmart_callback'):
            return res

        fields_to_sync = ['tag_mac', 'name', 'pickup_quantity']
        for record in self:
            if record.tag_mac and any(f in vals for f in fields_to_sync):
                try:
                    _logger.error("!!! CAMBIO MANUAL DETECTADO para %s. Sincronizando Hardware (LED ON).", record.name)
                    record._update_picksmart_tag(led_rgb="00ff00")
                except Exception as e:
                    _logger.error("!!! Error en sincronización manual: %s", str(e))
        return res

    def _update_picksmart_tag(self, led_rgb="00ff00"):
        self.ensure_one()
        
        params = self.env['ir.config_parameter'].sudo()
        router_ip = params.get_param('picksmart.router_ip') or '192.168.1.200'
        style_id = params.get_param('picksmart.style_id') or '50'

        led_state = "1" if led_rgb == "000000" else "0"

        payload = [{
            "mac": str(self.tag_mac).replace('CWT', '').strip(),
            "styleid": str(style_id),
            "mappingtype": "791",
            "productName": str(self.name or ''),
            "Stock": str(int(self.qty_available or 0)),
            "basketsQuantity": str(int(self.pickup_quantity or 0)),
            "ledstate": led_state,
            "ledrgb": str(led_rgb),
            "outtime": "30",
            "arrow": ""
        }]

        url = f"http://{router_ip}/wms/associate/updateScreen"
        headers = {'Content-Type': 'application/json'}
        try:
            _logger.error("!!! TRANSMITIENDO -> MAC: %s | STOCK: %s | PICKING: %s | RGB: %s", 
                         self.tag_mac, payload[0]['Stock'], payload[0]['basketsQuantity'], payload[0]['ledrgb'])
            requests.post(url, json=payload, headers=headers, timeout=5)
        except Exception as e:
            _logger.error("!!! Fallo de conexión con el Router: %s", str(e))