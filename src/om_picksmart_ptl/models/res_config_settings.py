from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # These names must match the XML 'name' attribute exactly
    picksmart_router_ip = fields.Char(
        string='Router IP', 
        config_parameter='picksmart.router_ip'
    )
    picksmart_style_id = fields.Char(
        string='Style ID', 
        config_parameter='picksmart.style_id'
    )