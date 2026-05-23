import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class StockPickingBatch(models.Model):
    _inherit = 'stock.picking.batch'

    def action_done(self):
        """
        Intercepta la validación de un Traslado por Lote o por Olas desde la interfaz Web.
        Consolida las cantidades de todos los albaranes agrupados para el hardware.
        """
        if self.env.context.get('is_picksmart_callback'):
            return super(StockPickingBatch, self).action_done()

        _logger.error("!!! INTERCEPCIÓN WEB LOTE/OLA -> Procesando consolidación para el Hardware.")
        
        # Diccionario para agrupar cantidades por producto en este lote
        # { product_template_id: {'qty': X, 'type': 'incoming'/'outgoing', 'tmpl': record} }
        totals_per_template = {}

        for picking in self.picking_ids:
            # Saltamos albaranes cancelados o ya hechos
            if picking.state in ['draft', 'cancel', 'done']:
                continue
                
            for move in picking.move_ids:
                template = move.product_id.product_tmpl_id
                if not template or not template.tag_mac:
                    continue

                tmpl_id = template.id
                if tmpl_id not in totals_per_template:
                    totals_per_template[tmpl_id] = {
                        'qty': 0.0,
                        'type': picking.picking_type_code,
                        'tmpl': template
                    }
                totals_per_template[tmpl_id]['qty'] += move.product_uom_qty

        # Si no hay productos con TAG en el lote, dejamos pasar a Odoo de forma nativa
        if not totals_per_template:
            return super(StockPickingBatch, self).action_done()

        # Aplicamos los cambios consolidados directamente en PostgreSQL
        for tmpl_id, data in totals_per_template.items():
            template = data['tmpl']
            total_qty = data['qty']
            
            # Determinamos el signo: Recepciones negativo, Entregas/Lotes de salida positivo
            final_value = -total_qty if data['type'] == 'incoming' else total_qty
            
            _logger.error("!!! HARDWARE LOTE -> Producto: %s | Total Agrupado: %s", template.name, final_value)
            
            self.env.cr.execute(
                "UPDATE product_template SET pickup_quantity = %s WHERE id = %s",
                (final_value, template.id)
            )
            self.env.cr.commit()
            template.invalidate_recordset(['pickup_quantity'])
            
            # Encendemos el LED según el tipo dominante del grupo
            try:
                color = "0000ff" if data['type'] == 'incoming' else "00ff00"
                template._update_picksmart_tag(led_rgb=color)
            except Exception as e:
                _logger.error("!!! Error enviando al lote HTTP: %s", str(e))

        raise UserError("Traslado por Lote / Ola enviado agrupado al Hardware PTL. Confirme operando los tags.")


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        """ Sigue protegiendo las operaciones individuales simples """
        if self.env.context.get('is_picksmart_callback'):
            return super(StockPicking, self).button_validate()

        # Si este albarán ya pertenece a un lote, delegamos la validación al lote
        if self.batch_id:
            return super(StockPicking, self).button_validate()

        if self.picking_type_code in ['incoming', 'outgoing']:
            _logger.error("!!! INTERCEPCIÓN WEB SIMPLE -> Preparando operación individual.")
            for move in self.move_ids:
                template = move.product_id.product_tmpl_id
                if template and template.tag_mac:
                    qty = move.product_uom_qty
                    final_value = -qty if self.picking_type_code == 'incoming' else qty
                    
                    self.env.cr.execute(
                        "UPDATE product_template SET pickup_quantity = %s WHERE id = %s",
                        (final_value, template.id)
                    )
                    self.env.cr.commit()
                    template.invalidate_recordset(['pickup_quantity'])
                    
                    try:
                        color = "0000ff" if self.picking_type_code == 'incoming' else "00ff00"
                        template._update_picksmart_tag(led_rgb=color)
                    except Exception as e:
                        _logger.error("!!! Error HTTP Simple: %s", str(e))

            raise UserError(f"Operación individual de {self.picking_type_code} enviada al Hardware.")
        
        return super(StockPicking, self).button_validate()