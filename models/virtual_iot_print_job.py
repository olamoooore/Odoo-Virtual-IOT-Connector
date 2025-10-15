# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class VirtualIoTPrintJob(models.Model):
    _name = 'virtual.iot.print.job'
    _description = 'Virtual IoT Print Job'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Job Reference',
        required=True,
        help='Reference identifier for the print job'
    )
    
    device_id = fields.Many2one(
        'virtual.iot.device',
        string='Virtual IoT Device',
        required=True,
        ondelete='cascade'
    )
    
    printer_id = fields.Many2one(
        'virtual.iot.printer',
        string='Printer',
        required=True,
        ondelete='cascade'
    )
    
    status = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='pending', required=True)
    
    layout_type = fields.Selection([
        ('receipt', 'Receipt'),
        ('kitchen', 'Kitchen Order'),
        ('label', 'Label'),
        ('report', 'Report'),
        ('test', 'Test Print')
    ], string='Layout Type', default='receipt', required=True)
    
    html_content = fields.Text(
        string='HTML Content',
        required=True,
        help='HTML content to be printed'
    )
    
    response_data = fields.Text(
        string='Response Data',
        readonly=True,
        help='Response data from the Virtual IoT service'
    )
    
    error_message = fields.Text(
        string='Error Message',
        readonly=True,
        help='Error message if the print job failed'
    )
    
    created_at = fields.Datetime(
        string='Created At',
        default=fields.Datetime.now,
        readonly=True
    )
    
    completed_at = fields.Datetime(
        string='Completed At',
        readonly=True
    )
    
    duration = fields.Float(
        string='Duration (seconds)',
        compute='_compute_duration',
        store=True,
        help='Time taken to complete the print job'
    )
    
    # Related fields for easier access
    device_name = fields.Char(
        related='device_id.name',
        string='Device Name',
        readonly=True,
        store=True
    )
    
    printer_name = fields.Char(
        related='printer_id.name',
        string='Printer Name',
        readonly=True,
        store=True
    )
    
    printer_type = fields.Selection(
        related='printer_id.printer_type',
        string='Printer Type',
        readonly=True,
        store=True
    )
    
    # Source information
    source_model = fields.Char(
        string='Source Model',
        help='Model that triggered this print job (e.g., pos.order)'
    )
    
    source_id = fields.Integer(
        string='Source ID',
        help='ID of the record that triggered this print job'
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user,
        help='User who initiated the print job'
    )
    
    @api.depends('created_at', 'completed_at')
    def _compute_duration(self):
        """Compute the duration of the print job"""
        for job in self:
            if job.created_at and job.completed_at:
                delta = job.completed_at - job.created_at
                job.duration = delta.total_seconds()
            else:
                job.duration = 0.0
    
    def retry_print_job(self):
        """Retry a failed print job"""
        self.ensure_one()
        
        if self.status not in ['failed', 'cancelled']:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Cannot Retry'),
                    'message': _('Only failed or cancelled jobs can be retried'),
                    'type': 'warning',
                }
            }
        
        # Reset job status
        self.write({
            'status': 'pending',
            'error_message': False,
            'response_data': False,
            'completed_at': False
        })
        
        # Send the print job again
        return self.printer_id.send_print_job(
            html_content=self.html_content,
            job_reference=self.name,
            layout_type=self.layout_type
        )
    
    def cancel_print_job(self):
        """Cancel a pending print job"""
        self.ensure_one()
        
        if self.status not in ['pending', 'processing']:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Cannot Cancel'),
                    'message': _('Only pending or processing jobs can be cancelled'),
                    'type': 'warning',
                }
            }
        
        self.write({
            'status': 'cancelled',
            'completed_at': fields.Datetime.now()
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Job Cancelled'),
                'message': _('Print job has been cancelled'),
                'type': 'success',
            }
        }
    
    def view_html_content(self):
        """View the HTML content of the print job"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('HTML Content - %s') % self.name,
            'res_model': 'virtual.iot.print.job',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('virtual_iot_connector.view_virtual_iot_print_job_html_form').id,
            'target': 'new',
        }
    
    @api.model
    def cleanup_old_jobs(self, days=30):
        """Clean up old print jobs (called by cron)"""
        cutoff_date = fields.Datetime.now() - timedelta(days=days)
        old_jobs = self.search([
            ('create_date', '<', cutoff_date),
            ('status', 'in', ['success', 'failed', 'cancelled'])
        ])
        
        count = len(old_jobs)
        old_jobs.unlink()
        
        return {
            'cleaned_jobs': count,
            'cutoff_date': cutoff_date
        }
    
    @api.model
    def get_statistics(self, domain=None):
        """Get print job statistics"""
        if domain is None:
            domain = []
        
        jobs = self.search(domain)
        
        return {
            'total': len(jobs),
            'pending': len(jobs.filtered(lambda j: j.status == 'pending')),
            'processing': len(jobs.filtered(lambda j: j.status == 'processing')),
            'success': len(jobs.filtered(lambda j: j.status == 'success')),
            'failed': len(jobs.filtered(lambda j: j.status == 'failed')),
            'cancelled': len(jobs.filtered(lambda j: j.status == 'cancelled')),
            'avg_duration': sum(jobs.mapped('duration')) / len(jobs) if jobs else 0,
        }