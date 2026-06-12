{
    'name': 'Picksmart PTL Integration',
    'version': '1.0',
    'category': 'Inventory',
    'summary': 'Sync Odoo Stock with Picksmart V24 Tags',
    'depends': [
        'base', 
        'stock', 
        'stock_picking_batch'  
    ],
    'author': "Ander Frago Landa",
    'data': [
        'security/ir.model.access.csv',
        'views/product_views.xml',
        # 'views/res_config_settings_views.xml',
        'views/picksmart_config_view.xml', # Add this
    ],
    'installable': True,
    'application': True,
}