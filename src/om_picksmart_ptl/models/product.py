import requests
import json
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    tag_mac = fields.Char(string="Tag MAC Address")
    pickup_quantity = fields.Float(string="Pickup Quantity", default=1.0)

    def write(self, vals):
        # 1. Perform the standard write
        res = super(ProductTemplate, self).write(vals)
        
        # 2. Check if we are in a callback
        # If 'is_picksmart_callback' is in context, we DON'T sync back to hardware
        if self.env.context.get('is_picksmart_callback'):
            return res

        # 3. Otherwise, proceed with normal sync (for manual changes in Odoo UI)
        fields_to_check = ['tag_mac', 'pickup_quantity', 'qty_available']
        if any(field in vals for field in fields_to_check):
            for record in self:
                if record.tag_mac:
                    try:
                        record._update_picksmart_tag()
                    except Exception as e:
                        _logger.error("Picksmart sync failed: %s", str(e))
        return res

    def _update_picksmart_tag(self):
        self.ensure_one()

        # IMPORTANT: Push changes to DB without closing the transaction
        # This ensures 'qty_available' is calculated and stored correctly
        self.flush_recordset(['qty_available', 'pickup_quantity'])
        
        params = self.env['ir.config_parameter'].sudo()
        router_ip = params.get_param('picksmart.router_ip') or '192.168.1.200'
        style_id = params.get_param('picksmart.style_id') or '50'

        # Note: In Odoo 19, use int() or float() carefully with qty_available
        qty = int(self.qty_available) if self.qty_available else 0
        pickup = int(self.pickup_quantity) if self.pickup_quantity else 0

        payload = [{
            "mac": str(self.tag_mac).replace('CWT', '').strip(),
            "styleid": str(style_id),
            "mappingtype": "791",
            "productName": str(self.name or ''),
            "Stock": str(qty),
            "basketsQuantity": str(pickup),
            "ledstate": "0",
            "ledrgb": "00ff00",
            "outtime": "30",
            "startMachine": "",
            "endMachine": "",
            "taskStartTime": "",
            "arrow": "",
            "rssi": "",
            "power": ""
        }]

        url = f"http://{router_ip}/wms/associate/updateScreen"
        headers = {'Content-Type': 'application/json'}
        
        try:
            # Added a short timeout so the Odoo UI doesn't hang if the router is offline
            response = requests.post(url, json=payload, headers=headers, timeout=3)
            _logger.info("Sent update to Tag %s. Status: %s", self.tag_mac, response.status_code)
        except Exception as e:
            _logger.error("Sync failed for MAC %s: %s", self.tag_mac, str(e))