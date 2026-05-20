from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Los nombres de los campos DEBEN coincidir exactamente con tu XML
    picksmart_router_ip = fields.Char(
        string="Picksmart Router IP",
        config_parameter='picksmart.router_ip', # Guarda automáticamente en ir.config_parameter
        default='192.168.1.200'
    )
    
    picksmart_style_id = fields.Char(
        string="Picksmart Style ID",
        config_parameter='picksmart.style_id', # Guarda automáticamente en ir.config_parameter
        default='50'
    )