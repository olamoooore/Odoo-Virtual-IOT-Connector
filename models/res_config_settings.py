# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Virtual IoT Device field for domain filtering
    pos_virtual_iot_device_id = fields.Many2one(
        related='pos_config_id.virtual_iot_device_id',
        readonly=True,
        string='Virtual IoT Device'
    )

    # Virtual IoT Preparation Printer field for POS configuration settings
    pos_virtual_preparation_printer_id = fields.Many2one(
        related='pos_config_id.virtual_preparation_printer_id',
        readonly=False,
        string='Virtual Preparation Printer'
    )