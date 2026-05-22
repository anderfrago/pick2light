import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        # Evitamos interceptar si la orden ya viene procesada por el hardware
        if self.env.context.get('is_picksmart_callback'):
            return super(StockPicking, self).button_validate()

        # -------------------------------------------------------------------------
        # 1. FLUJO DE ENTRADAS (RECEPCIONES)
        # -------------------------------------------------------------------------
        if self.picking_type_code == 'incoming':
            _logger.error("!!! INTERCEPCIÓN WEB -> Preparando Entrada Persistente (Negativa).")
            for move in self.move_ids:
                template = move.product_id.product_tmpl_id
                if template and template.tag_mac:
                    qty = move.product_uom_qty
                    
                    # Escritura directa en SQL para saltar el Rollback del UserError
                    self.env.cr.execute(
                        "UPDATE product_template SET pickup_quantity = %s WHERE id = %s",
                        (-qty, template.id)
                    )
                    self.env.cr.commit()
                    template.invalidate_recordset(['pickup_quantity'])
                    
                    try:
                        template._update_picksmart_tag(led_rgb="0000ff") # Azul para Entradas
                    except Exception as e:
                        _logger.error("!!! Error HTTP Tag Entrada: %s", str(e))

            raise UserError("Operación de ENTRADA enviada al Hardware. Confirme pulsando el Botón 0 en la etiqueta.")

        # -------------------------------------------------------------------------
        # 2. FLUJO DE SALIDAS (ENTREGAS / PICKING DE PEDIDOS)
        # -------------------------------------------------------------------------
        elif self.picking_type_code == 'outgoing':
            _logger.error("!!! INTERCEPCIÓN WEB -> Preparando Salida Persistente (Positiva).")
            for move in self.move_ids:
                template = move.product_id.product_tmpl_id
                if template and template.tag_mac:
                    qty = move.product_uom_qty
                    
                    # Para las salidas guardamos el valor POSITIVO puro en la base de datos
                    self.env.cr.execute(
                        "UPDATE product_template SET pickup_quantity = %s WHERE id = %s",
                        (qty, template.id)
                    )
                    self.env.cr.commit()
                    template.invalidate_recordset(['pickup_quantity'])
                    
                    try:
                        template._update_picksmart_tag(led_rgb="00ff00") # Verde (o "ff0000" Rojo) para Salidas
                    except Exception as e:
                        _logger.error("!!! Error HTTP Tag Salida: %s", str(e))

            raise UserError("Operación de SALIDA enviada al Hardware. Retire el producto y confirme pulsando el Botón 0.")
        
        return super(StockPicking, self).button_validate()


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_assign(self, force_qty=False):
        """ Salvavidas por si el usuario pulsa 'Comprobar Disponibilidad' en la web """
        res = super(StockMove, self)._action_assign(force_qty=force_qty)
        if self.env.context.get('is_picksmart_callback'):
            return res

        for move in self:
            template = move.product_id.product_tmpl_id
            if template and template.tag_mac and template.pickup_quantity == 0.0:
                qty = move.product_uom_qty
                
                if move.picking_id.picking_type_code == 'incoming':
                    template.with_context(is_picksmart_callback=True).write({'pickup_quantity': -qty})
                    template.invalidate_recordset(['pickup_quantity'])
                    template._update_picksmart_tag(led_rgb="0000ff")
                    
                elif move.picking_id.picking_type_code == 'outgoing':
                    template.with_context(is_picksmart_callback=True).write({'pickup_quantity': qty})
                    template.invalidate_recordset(['pickup_quantity'])
                    template._update_picksmart_tag(led_rgb="00ff00")
        return res