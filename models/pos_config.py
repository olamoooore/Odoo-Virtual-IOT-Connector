# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    _inherit = 'pos.config'

    # Virtual IoT Device Configuration
    virtual_iot_device_id = fields.Many2one(
        'virtual.iot.device',
        string='Virtual IoT Device',
        help='Virtual IoT device for this POS configuration'
    )
    
    # Printer Mappings
    virtual_receipt_printer_id = fields.Many2one(
        'virtual.iot.printer',
        string='Receipt Printer',
        domain="[('device_id', '=', virtual_iot_device_id), ('printer_type', '=', 'receipt'), ('active', '=', True)]",
        help='Virtual IoT printer for receipts'
    )
    
    virtual_kitchen_printer_id = fields.Many2one(
        'virtual.iot.printer',
        string='Kitchen Printer',
        domain="[('device_id', '=', virtual_iot_device_id), ('printer_type', '=', 'kitchen'), ('active', '=', True)]",
        help='Virtual IoT printer for kitchen orders'
    )
    
    virtual_label_printer_id = fields.Many2one(
        'virtual.iot.printer',
        string='Label Printer',
        domain="[('device_id', '=', virtual_iot_device_id), ('printer_type', '=', 'label'), ('active', '=', True)]",
        help='Virtual IoT printer for labels'
    )
    
    virtual_report_printer_id = fields.Many2one(
        'virtual.iot.printer',
        string='Report Printer',
        domain="[('device_id', '=', virtual_iot_device_id), ('printer_type', '=', 'report'), ('active', '=', True)]",
        help='Virtual IoT printer for reports'
    )
    
    virtual_preparation_printer_id = fields.Many2one(
        'virtual.iot.printer',
        string='Virtual Preparation Printer',
        domain="[('device_id', '=', virtual_iot_device_id), ('printer_type', 'in', ['kitchen', 'receipt']), ('active', '=', True)]",
        help='Virtual IoT printer for preparation orders (can use kitchen or receipt printers)'
    )
    
    # Virtual IoT Settings
    use_virtual_iot = fields.Boolean(
        string='Use Virtual IoT',
        default=False,
        help='Enable Virtual IoT for this POS configuration'
    )
    
    virtual_iot_auto_print_receipt = fields.Boolean(
        string='Auto Print Receipt',
        default=True,
        help='Automatically print receipt after order completion'
    )
    
    virtual_iot_auto_print_kitchen = fields.Boolean(
        string='Auto Print Kitchen Order',
        default=False,
        help='Automatically print kitchen order'
    )
    
    virtual_iot_print_kitchen_on_payment = fields.Boolean(
        string='Print Kitchen on Payment',
        default=True,
        help='Print kitchen order when payment is made'
    )
    
    @api.constrains('virtual_iot_device_id', 'virtual_receipt_printer_id', 'virtual_kitchen_printer_id', 'virtual_label_printer_id', 'virtual_report_printer_id', 'virtual_preparation_printer_id')
    def _check_virtual_iot_printers(self):
        """Validate that all selected printers belong to the selected device"""
        for config in self:
            if config.use_virtual_iot and config.virtual_iot_device_id:
                printers = [
                    config.virtual_receipt_printer_id,
                    config.virtual_kitchen_printer_id,
                    config.virtual_label_printer_id,
                    config.virtual_report_printer_id,
                    config.virtual_preparation_printer_id
                ]
                
                for printer in printers:
                    if printer and printer.device_id != config.virtual_iot_device_id:
                        raise ValidationError(
                            _('All selected printers must belong to the selected Virtual IoT device (%s)') 
                            % config.virtual_iot_device_id.name
                        )
    
    @api.onchange('virtual_iot_device_id')
    def _onchange_virtual_iot_device_id(self):
        """Clear printer selections when device changes"""
        if self.virtual_iot_device_id:
            # Clear existing printer selections
            self.virtual_receipt_printer_id = False
            self.virtual_kitchen_printer_id = False
            self.virtual_label_printer_id = False
            self.virtual_report_printer_id = False
            self.virtual_preparation_printer_id = False
        else:
            self.use_virtual_iot = False
    
    @api.onchange('use_virtual_iot')
    def _onchange_use_virtual_iot(self):
        """Clear Virtual IoT settings when disabled"""
        if not self.use_virtual_iot:
            self.virtual_iot_device_id = False
            self.virtual_receipt_printer_id = False
            self.virtual_kitchen_printer_id = False
            self.virtual_label_printer_id = False
            self.virtual_report_printer_id = False
            self.virtual_preparation_printer_id = False
    
    def test_virtual_iot_connection(self):
        """Test connection to the Virtual IoT device"""
        self.ensure_one()
        
        if not self.virtual_iot_device_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Device Selected'),
                    'message': _('Please select a Virtual IoT device first'),
                    'type': 'warning',
                }
            }
        
        return self.virtual_iot_device_id.test_connection()
    
    def sync_virtual_iot_printers(self):
        """Sync printers from the Virtual IoT device"""
        self.ensure_one()
        
        if not self.virtual_iot_device_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Device Selected'),
                    'message': _('Please select a Virtual IoT device first'),
                    'type': 'warning',
                }
            }
        
        return self.virtual_iot_device_id.sync_printers()
    
    def print_receipt(self, order_data, html_content):
        """Print receipt using Virtual IoT"""
        self.ensure_one()
        
        if not self.use_virtual_iot or not self.virtual_receipt_printer_id:
            return False
        
        return self.virtual_receipt_printer_id.send_print_job(
            html_content=html_content,
            job_reference=f"RECEIPT-{order_data.get('name', 'UNKNOWN')}",
            layout_type='receipt'
        )
    
    def print_kitchen_order(self, order_data, html_content):
        """Print kitchen order using Virtual IoT"""
        self.ensure_one()
        
        if not self.use_virtual_iot or not self.virtual_kitchen_printer_id:
            return False
        
        return self.virtual_kitchen_printer_id.send_print_job(
            html_content=html_content,
            job_reference=f"KITCHEN-{order_data.get('name', 'UNKNOWN')}",
            layout_type='kitchen'
        )
    
    def print_label(self, label_data, html_content):
        """Print label using Virtual IoT"""
        self.ensure_one()
        
        if not self.use_virtual_iot or not self.virtual_label_printer_id:
            return False
        
        return self.virtual_label_printer_id.send_print_job(
            html_content=html_content,
            job_reference=f"LABEL-{label_data.get('reference', 'UNKNOWN')}",
            layout_type='label'
        )
    
    def print_report(self, report_data, html_content):
        """Print report using Virtual IoT"""
        self.ensure_one()
        
        if not self.use_virtual_iot or not self.virtual_report_printer_id:
            return False
        
        return self.virtual_report_printer_id.send_print_job(
            html_content=html_content,
            job_reference=f"REPORT-{report_data.get('name', 'UNKNOWN')}",
            layout_type='report'
        )
    
    def get_virtual_iot_status(self):
        """Get Virtual IoT status for this POS configuration"""
        self.ensure_one()
        
        if not self.use_virtual_iot or not self.virtual_iot_device_id:
            return {
                'enabled': False,
                'device_status': 'not_configured'
            }
        
        device = self.virtual_iot_device_id
        printers = {
            'receipt': self.virtual_receipt_printer_id,
            'kitchen': self.virtual_kitchen_printer_id,
            'label': self.virtual_label_printer_id,
            'report': self.virtual_report_printer_id
        }
        
        printer_status = {}
        for printer_type, printer in printers.items():
            if printer:
                printer_status[printer_type] = {
                    'name': printer.name,
                    'status': printer.status
                }
            else:
                printer_status[printer_type] = None
        
        return {
            'enabled': True,
            'device_name': device.name,
            'device_status': device.status,
            'device_last_seen': device.last_seen,
            'printers': printer_status
        }