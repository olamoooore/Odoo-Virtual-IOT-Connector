# -*- coding: utf-8 -*-
{
    'name': 'Virtual IoT Connector',
    'version': '18.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Virtual IoT Bridge for Odoo - Replace physical IoT Box with software solution',
    'description': """
Virtual IoT Connector
=====================

This module provides a virtual IoT solution that replaces the physical Odoo IoT Box.
It enables seamless printer management and print job routing for POS and backend operations.

Key Features:
- Virtual IoT device registration and management
- Printer auto-detection and mapping
- Real-time print job routing
- Support for receipt, kitchen, and label printers
- Secure REST API communication
- HTML/PDF layout preservation

The module works in conjunction with a local Virtual IoT Service that handles
the actual printer communication and rendering.
    """,
    'author': 'Olaniyan Olaide',
    'website': 'https://github.com/virtual-iot',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'point_of_sale',
        'web',
        'pos_receipt_custom',
    ],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'data/system_parameters.xml',
        'views/pos_config_views.xml',
        'views/res_config_settings_views.xml',
        'views/virtual_iot_printer_views.xml',
        'views/virtual_iot_device_views.xml',
        'views/virtual_iot_menu.xml',
         'views/virtual_iot_security_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'virtual_iot_connector/static/src/js/virtual_iot_service.js',
            'virtual_iot_connector/static/src/xml/dashboard_template.xml',
        ],
        'point_of_sale._assets_pos': [
            'virtual_iot_connector/static/src/js/pos_virtual_iot.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}