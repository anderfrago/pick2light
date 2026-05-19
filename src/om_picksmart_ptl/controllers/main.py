from odoo import http, fields
from odoo.http import request
import json
import logging
import requests

_logger = logging.getLogger(__name__)

class PicksmartController(http.Controller):

    def _set_on_hand_quantity(self, product, new_quantity):
        """
        Finds the existing quant for the internal location and overwrites it.
        This prevents the 'adding/summing' issue.
        """
        variant = product.product_variant_id
        # Find the primary internal storage location
        location = request.env['stock.location'].sudo().search([
            ('usage', '=', 'internal')
        ], limit=1)

        if not location:
            _logger.error("No internal location found to adjust stock.")
            return

        # Search for an existing quant record for this product in this location
        quant = request.env['stock.quant'].sudo().search([
            ('product_id', '=', variant.id),
            ('location_id', '=', location.id)
        ], limit=1)

        _logger.info("!!! REPLACING STOCK: %s to exactly %s", product.name, new_quantity)

        if quant:
            # If it exists, overwrite the 'inventory_quantity' field
            quant.with_context(inventory_mode=True, is_picksmart_callback=True).write({
                'inventory_quantity': new_quantity
            })
        else:
            # If no quant exists yet, create a new one
            quant = request.env['stock.quant'].sudo().with_context(
                inventory_mode=True, 
                is_picksmart_callback=True
            ).create({
                'product_id': variant.id,
                'location_id': location.id,
                'inventory_quantity': new_quantity,
            })
        
        # Apply the adjustment to generate the stock move and update qty_available
        quant.action_apply_inventory()
        
        # Force cache invalidation so the UI sees the change immediately
        variant._compute_quantities()
        product.invalidate_recordset(['qty_available'], [product.id])
        product.flush_recordset(['qty_available'])

    @http.route('/picksmart/callback', type='http', auth='public', methods=['POST'], csrf=False)
    def tag_callback(self, **post):
        try:
            # 1. Parse Incoming JSON
            data = json.loads(request.httprequest.data)
            _logger.info("!!! PICKSMART CALLBACK DATA: %s", data)
            
            button_result = data.get('result') 
            mac_raw = data.get('mac')
            
            # 2. Search for Product
            product = request.env['product.template'].sudo().search([
                '|', ('tag_mac', '=', str(mac_raw)), 
                ('tag_mac', '=', str(mac_raw).replace('CWT', '').strip())
            ], limit=1)
            
            if not product:
                return request.make_response(json.dumps({"status": "not_found"}), status=404)

            # Use a context-aware record to prevent infinite blink loops
            product_ctx = product.with_context(is_picksmart_callback=True)

            # 3. Button Logic (REPLACE values for 1 and 3)
            if button_result == 0:
                # Add current pickup_quantity to current stock
                new_total = product_ctx.qty_available - product_ctx.pickup_quantity
                self._set_on_hand_quantity(product_ctx, new_total)
                product_ctx.write({'pickup_quantity': 0})
                
            elif button_result == 1:
                new_total = product_ctx.qty_available + 1
                self._set_on_hand_quantity(product_ctx, new_total)
                
            elif button_result == 3:
                new_total = product_ctx.qty_available + 3
                self._set_on_hand_quantity(product_ctx, new_total)

            # 4. Finalize DB Changes
            request.env.cr.commit()

            # 5. UI Refresh (The Bus)
            # Targeting 'authenticated_user' is more reliable than 'public' in Odoo 19
            bus = request.env['bus.bus'].sudo()
            bus._sendone('authenticated_user', 'mail.record/insert', {
                'Model': 'product.template',
                'Id': product.id,
                'data': {
                    'qty_available': product.qty_available,
                    'pickup_quantity': product.pickup_quantity,
                }
            })
            bus._sendone('authenticated_user', 'ir.actions.client', {'tag': 'reload'})

            # 6. Hardware Sync (Silent update of the tag screen)
            self._sync_hardware_silent(product)

            return request.make_response(json.dumps({"status": "success"}), headers={'Content-Type': 'application/json'})
            
        except Exception as e:
            _logger.error("Picksmart callback error: %s", str(e))
            return request.make_response(json.dumps({"status": "error", "message": str(e)}), status=500)

    def _sync_hardware_silent(self, product):
        """ Sends the updated numbers back to the tag without lighting the LED """
        params = request.env['ir.config_parameter'].sudo()
        router_ip = params.get_param('picksmart.router_ip') or '192.168.1.200'
        style_id = params.get_param('picksmart.style_id') or '50'
        
        payload = [{
            "mac": str(product.tag_mac).replace('CWT', '').strip(),
            "styleid": str(style_id),
            "mappingtype": "791",
            "productName": str(product.name or ''),
            "Stock": str(int(product.qty_available)),
            "basketsQuantity": str(int(product.pickup_quantity)),
            "ledstate": "0", # Ensure LED is OFF
            "ledrgb": "000000",
            "outtime": "30"
        }]
        
        try:
            url = f"http://{router_ip}/wms/associate/updateScreen"
            requests.post(url, json=payload, timeout=3)
        except Exception as e:
            _logger.error("Hardware sync failed: %s", str(e))