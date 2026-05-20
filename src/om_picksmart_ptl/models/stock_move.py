from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class StockMove(models.Model):
    _inherit = 'stock.move'

    def write(self, vals):
        res = super(StockMove, self).write(vals)
        
        
        if 'state' in vals:
            # SI EL ESTADO NUEVO ES 'DONE' (O CANCEL), SIGNIFICA QUE ALGUIEN 
            # LO HA VALIDADO DESDE EL ORDENADOR. NO QUEREMOS QUE ENVIÉ NADA AL HARDWARE.
            if vals.get('state') in ['done', 'cancel']:
                return res # Salimos del código y que Odoo haga su inventario en silencio.


            moves_with_picking = self.filtered(lambda m: m.picking_id)
            if not moves_with_picking:
                return res
                
            templates_to_update = moves_with_picking.mapped('product_id.product_tmpl_id')
            
            # -------------------------------------------------------------------------
            # DETECCIÓN ENTRE WORKERS: Descartamos la caché local de Odoo y leemos
            # directamente el valor real guardado en las tablas de PostgreSQL.
            # -------------------------------------------------------------------------
            templates_to_update.invalidate_recordset(['is_hardware_updating'])
            
            for template in templates_to_update:
                if template.is_hardware_updating:
                    _logger.error("!!! StockMove: Bloqueo inter-proceso detectado (Worker ocupado con botón 0). Abortando señal verde.")
                    return res

            valid_states = ['confirmed', 'assigned', 'partially_available']
            
            for template in templates_to_update:
                if template.tag_mac:
                    outbound = 0.0
                    inbound = 0.0
                    for variant in template.product_variant_ids:
                        m_active = variant.stock_move_ids.filtered(lambda m: m.state in valid_states and m.picking_id)
                        outbound += sum(m_active.filtered(lambda m: m.picking_code == 'outgoing').mapped('product_uom_qty'))
                        inbound += sum(m_active.filtered(lambda m: m.picking_code == 'incoming').mapped('product_uom_qty'))
                    
                    template_ctx = template.with_context(is_picksmart_callback=True)
                    
                    if outbound > 0:
                        template_ctx.pickup_quantity = outbound
                    elif inbound > 0:
                        template_ctx.pickup_quantity = -inbound
                    else:
                        template_ctx.pickup_quantity = 0.0
                        
                    _logger.error("!!! StockMove: Nueva orden detectada en Odoo. Inicializando pantalla en verde.")
                    template_ctx._update_picksmart_tag(led_rgb="00ff00")
        return res