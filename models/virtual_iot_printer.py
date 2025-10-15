# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
import base64
import tempfile
import os

_logger = logging.getLogger(__name__)


class VirtualIoTPrinter(models.Model):
    _name = 'virtual.iot.printer'
    _description = 'Virtual IoT Printer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(
        string='Printer Name',
        required=True,
        help='Name of the printer as detected by the system'
    )
    
    device_id = fields.Many2one(
        'virtual.iot.device',
        string='Virtual IoT Device',
        required=True,
        ondelete='cascade',
        help='Virtual IoT device this printer is connected to'
    )
    
    printer_type = fields.Selection([
        ('receipt', 'Receipt Printer'),
        ('kitchen', 'Kitchen Printer'),
        ('label', 'Label Printer'),
        ('report', 'Report Printer')
    ], string='Printer Type', default='receipt', required=True)
    
    connection_type = fields.Selection([
        ('network', 'Network'),
        ('usb', 'USB'),
        ('serial', 'Serial'),
        ('system', 'System')
    ], string='Connection Type', default='network', required=True,
       help='Type of connection used to communicate with the printer')
    
    device_path = fields.Char(
        string='Device Path',
        help='Device path for USB/Serial printers (e.g., /dev/ttyUSB0, COM3)'
    )
    
    ip_address = fields.Char(
        string='IP Address',
        help='IP address for network printers'
    )
    
    port = fields.Integer(
        string='Port',
        help='Port number for network printers'
    )
    
    status = fields.Selection([
        ('ready', 'Ready'),
        ('busy', 'Busy'),
        ('offline', 'Offline'),
        ('error', 'Error')
    ], string='Status', default='ready', readonly=True)
    
    last_job_time = fields.Datetime(
        string='Last Job Time',
        readonly=True,
        help='Time of the last print job'
    )
    
    print_job_ids = fields.One2many(
        'virtual.iot.print.job',
        'printer_id',
        string='Print Jobs',
        help='Print jobs sent to this printer'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )
    
    # Technical fields for printer configuration
    paper_width = fields.Integer(
        string='Paper Width (mm)',
        default=80,
        help='Paper width in millimeters'
    )
    
    paper_height = fields.Integer(
        string='Paper Height (mm)',
        default=0,
        help='Paper height in millimeters (0 for continuous)'
    )
    
    dpi = fields.Integer(
        string='DPI',
        default=203,
        help='Dots per inch resolution'
    )
    
    margin_top = fields.Integer(
        string='Top Margin (mm)',
        default=5
    )
    
    margin_bottom = fields.Integer(
        string='Bottom Margin (mm)',
        default=5
    )
    
    margin_left = fields.Integer(
        string='Left Margin (mm)',
        default=5
    )
    
    margin_right = fields.Integer(
        string='Right Margin (mm)',
        default=5
    )
    
    # Statistics
    total_jobs = fields.Integer(
        string='Total Jobs',
        compute='_compute_statistics',
        store=True
    )
    
    successful_jobs = fields.Integer(
        string='Successful Jobs',
        compute='_compute_statistics',
        store=True
    )
    
    failed_jobs = fields.Integer(
        string='Failed Jobs',
        compute='_compute_statistics',
        store=True
    )
    
    @api.depends('print_job_ids.status')
    def _compute_statistics(self):
        """Compute printer statistics"""
        for printer in self:
            jobs = printer.print_job_ids
            printer.total_jobs = len(jobs)
            printer.successful_jobs = len(jobs.filtered(lambda j: j.status == 'success'))
            printer.failed_jobs = len(jobs.filtered(lambda j: j.status == 'failed'))
    
    def test_printer(self):
        """Send a test print to the printer"""
        self.ensure_one()
        
        if self.device_id.status != 'online':
            raise UserError(_('Device %s is not online') % self.device_id.name)
        
        test_html = """
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .header { text-align: center; font-weight: bold; font-size: 18px; }
                .info { margin: 10px 0; }
                .footer { text-align: center; margin-top: 20px; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="header">TEST PRINT</div>
            <div class="info">Printer: %s</div>
            <div class="info">Type: %s</div>
            <div class="info">Device: %s</div>
            <div class="info">Time: %s</div>
            <div class="footer">Virtual IoT Connector Test</div>
        </body>
        </html>
        """ % (
            self.name,
            dict(self._fields['printer_type'].selection)[self.printer_type],
            self.device_id.name,
            fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        
        return self.send_print_job(
            html_content=test_html,
            job_reference='TEST-PRINT',
            layout_type=self.printer_type
        )
    
    def _get_virtual_iot_printer_id(self):
        """Get the printer ID from the Virtual IoT service by matching the printer name"""
        try:
            url = f"{self.device_id._get_base_url()}/printers"
            response = requests.get(url, headers=self.device_id._get_headers(), timeout=10)
            
            if response.status_code == 200:
                printers = response.json()
                _logger.info(f"Available printers in Virtual IoT service: {[p.get('name') for p in printers]}")
                
                # Try to find printer by exact name match first
                for printer in printers:
                    if printer.get('name') == self.name:
                        _logger.info(f"Found exact match for printer '{self.name}' (ID: {printer.get('id')})")
                        return printer.get('id')
                
                # If no exact match, try various matching strategies
                our_name_lower = self.name.lower()
                our_name_parts = [part for part in our_name_lower.split() if len(part) > 2]
                
                for printer in printers:
                    printer_name = printer.get('name', '').lower()
                    printer_id = printer.get('id')
                    
                    # Strategy 1: Check if printer name contains our name parts
                    if any(part in printer_name for part in our_name_parts):
                        _logger.info(f"Matched printer '{self.name}' to Virtual IoT printer '{printer.get('name')}' (ID: {printer_id}) - Strategy 1")
                        return printer_id
                    
                    # Strategy 2: Check if our name contains printer name parts
                    printer_parts = [part for part in printer_name.split() if len(part) > 2]
                    if any(part in our_name_lower for part in printer_parts):
                        _logger.info(f"Matched printer '{self.name}' to Virtual IoT printer '{printer.get('name')}' (ID: {printer_id}) - Strategy 2")
                        return printer_id
                
                # Strategy 3: Try to match by IP address if available
                if hasattr(self, 'ip_address') and self.ip_address:
                    for printer in printers:
                        printer_name = printer.get('name', '')
                        if self.ip_address in printer_name:
                            _logger.info(f"Matched printer '{self.name}' to Virtual IoT printer '{printer.get('name')}' (ID: {printer.get('id')}) by IP address")
                            return printer.get('id')
                
                _logger.warning(f"No matching printer found for '{self.name}' in Virtual IoT service. Available printers: {[p.get('name') for p in printers]}")
                return None
            else:
                if response.status_code == 401:
                    _logger.error(f"Authentication failed - Invalid API key for Virtual IoT service")
                    # Update device status to indicate auth issue
                    self.device_id.status = 'error'
                elif response.status_code == 404:
                    _logger.error(f"Virtual IoT service endpoint not found - service may not be running")
                    self.device_id.status = 'offline'
                else:
                    _logger.error(f"Failed to get printers from Virtual IoT service: {response.status_code} - {response.text}")
                    self.device_id.status = 'error'
                return None
                
        except Exception as e:
            _logger.error(f"Error getting printer ID from Virtual IoT service: {e}")
            return None

    def register_printer_with_virtual_iot(self):
        """Register this printer with the Virtual IoT service"""
        try:
            url = f"{self.device_id._get_base_url()}/printers"
            payload = {
                'name': self.name,
                'type': self.printer_type,
                'connection_type': self.connection_type,
                'ip_address': self.ip_address,
                'port': self.port,
                'device_path': self.device_path,
                'paper_width': self.paper_width,
                'paper_height': self.paper_height,
                'dpi': self.dpi
            }
            
            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}
            
            response = requests.post(
                url,
                json=payload,
                headers=self.device_id._get_headers(),
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                printer_id = result.get('id')
                _logger.info(f"Successfully registered printer '{self.name}' with Virtual IoT service (ID: {printer_id})")
                return printer_id
            else:
                _logger.error(f"Failed to register printer with Virtual IoT service: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            _logger.error(f"Error registering printer with Virtual IoT service: {e}")
            return None

    def _convert_html_to_pdf(self, html_content):
        """Convert HTML content to PDF or fallback to formatted HTML"""
        try:
            # Validate HTML content first
            if not html_content or not html_content.strip():
                _logger.error("Empty HTML content provided for printing")
                raise ValueError("Empty HTML content")
            
            # Try to use Odoo's wkhtmltopdf functionality if available
            try:
                # Ensure HTML content is properly formatted
                if not html_content.strip().startswith('<!DOCTYPE') and not html_content.strip().startswith('<html'):
                    # Wrap HTML fragment with proper document structure
                    formatted_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ 
            margin: 0; 
            padding: 5mm; 
            font-family: Arial, sans-serif; 
            font-size: 12px; 
            line-height: 1.2;
        }}
        * {{ box-sizing: border-box; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
                else:
                    formatted_html = html_content
                
                # Create a temporary HTML file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as html_file:
                    html_file.write(formatted_html)
                    html_file_path = html_file.name
                
                try:
                    # Convert HTML to PDF using wkhtmltopdf
                    # Use receipt-specific options for better formatting
                    options = {
                        'page-size': 'A4',
                        'margin-top': '5mm',
                        'margin-right': '5mm', 
                        'margin-bottom': '5mm',
                        'margin-left': '5mm',
                        'encoding': 'UTF-8',
                        'no-outline': None,
                        'disable-smart-shrinking': None,
                    }
                    
                    # For receipt printers, use smaller page size
                    if self.printer_type == 'receipt':
                        options.update({
                            'page-width': '80mm',
                            'page-height': '200mm',
                            'margin-top': '2mm',
                            'margin-right': '2mm',
                            'margin-bottom': '2mm', 
                            'margin-left': '2mm',
                        })
                    elif self.printer_type == 'kitchen':
                        # Kitchen stickers are typically small format
                        options.update({
                            'page-width': '50mm',
                            'page-height': '37mm',
                            'margin-top': '1mm',
                            'margin-right': '1mm',
                            'margin-bottom': '1mm', 
                            'margin-left': '1mm',
                        })
                    
                    # Generate PDF
                    pdf_content = self.env['ir.actions.report']._run_wkhtmltopdf(
                        [html_file_path],
                        specific_paperformat_args=options
                    )
                    
                    _logger.info("Successfully converted HTML to PDF using wkhtmltopdf")
                    return base64.b64encode(pdf_content).decode('utf-8')
                    
                finally:
                    # Clean up temporary file
                    if os.path.exists(html_file_path):
                        os.unlink(html_file_path)
                        
            except Exception as pdf_error:
                _logger.warning(f"wkhtmltopdf not available or failed: {pdf_error}")
                
                # Fallback: Create properly formatted HTML file for printing
                # Preserve original document styling to prevent blank prints
                if html_content.strip().startswith('<!DOCTYPE') or html_content.strip().startswith('<html'):
                    # Content is already a complete HTML document, use as-is
                    formatted_html = html_content
                else:
                    # Content is HTML fragment, wrap with proper structure and basic styling
                    formatted_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ 
            margin: 0; 
            padding: 5mm; 
            font-family: Arial, sans-serif; 
            font-size: 12px; 
            line-height: 1.2;
            background: white;
            color: black;
        }}
        * {{ box-sizing: border-box; }}
        div {{ display: block; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
                
                # Create a temporary HTML file and return its path
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_file:
                    temp_file.write(formatted_html)
                    temp_file_path = temp_file.name
                
                _logger.info(f"Created formatted HTML file for printing: {temp_file_path}")
                return temp_file_path
                
        except Exception as e:
            _logger.error(f"Failed to process HTML content: {e}")
            # Final fallback: return base64 encoded original HTML with validation
            if html_content and html_content.strip():
                return base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
            else:
                # Return a minimal test content if original is empty
                test_content = "<div>Test Print Content</div>"
                return base64.b64encode(test_content.encode('utf-8')).decode('utf-8')

    def send_print_job(self, html_content, job_reference=None, layout_type='receipt', source_model=None, source_id=None):
        """Send a print job to this printer"""
        self.ensure_one()
        
        if self.device_id.status != 'online':
            raise UserError(_('Device %s is not online') % self.device_id.name)
        
        # Create print job record
        print_job = self.env['virtual.iot.print.job'].create({
            'name': job_reference or f'Print Job {fields.Datetime.now()}',
            'device_id': self.device_id.id,
            'printer_id': self.id,
            'html_content': html_content,
            'layout_type': layout_type,
            'status': 'pending',
            'source_model': source_model,
            'source_id': source_id
        })
        
        try:
            # Get the printer ID from the Virtual IoT service
            printer_id = self._get_virtual_iot_printer_id()
            if not printer_id:
                # Check if the device is properly configured and online
                if self.device_id.status != 'online':
                    raise UserError(_(
                        'Virtual IoT device "%s" is not online. Please:\n'
                        '1. Ensure the Virtual IoT service is running\n'
                        '2. Test the device connection\n'
                        '3. Check the API key configuration'
                    ) % self.device_id.name)
                
                # Suggest syncing printers instead of auto-registration
                raise UserError(_(
                    'Printer "%s" not found in Virtual IoT service.\n\n'
                    'Please:\n'
                    '1. Go to Virtual IoT → Devices\n'
                    '2. Open your device "%s"\n'
                    '3. Click "Sync Printers" to discover available printers\n'
                    '4. Try the print test again\n\n'
                    'If the issue persists, check that:\n'
                    '• The Virtual IoT service is running\n'
                    '• The printer is properly connected\n'
                    '• The API key is correct'
                ) % (self.name, self.device_id.name))
            
            # Validate HTML content before processing
            if not html_content or not html_content.strip():
                _logger.error(f"Empty HTML content provided for print job {job_reference}")
                print_job.write({
                    'status': 'failed',
                    'error_message': 'Empty HTML content provided',
                    'completed_at': fields.Datetime.now()
                })
                return False
            
            # For cup printers (thermal printers), send original HTML directly
            # For other printer types, convert HTML to PDF for better formatting
            if self.printer_type in ['receipt', 'kitchen'] or 'cup' in self.name.lower():
                # Send original HTML content for thermal/cup printers
                _logger.info(f"Sending original HTML content for thermal printer {self.name}")
                content_type = 'html'
                file_path = None
                pdf_content = None
                
                # Ensure HTML content is properly formatted for direct sending
                if not html_content.strip().startswith('<!DOCTYPE') and not html_content.strip().startswith('<html'):
                    # Wrap HTML fragment with minimal structure
                    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ margin: 0; padding: 2mm; font-family: Arial, sans-serif; font-size: 12px; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
            else:
                # Convert HTML to PDF for other printer types (label, report printers)
                _logger.info(f"Converting HTML content for printer {self.name}")
                converted_content = self._convert_html_to_pdf(html_content)
                
                # Determine content type based on conversion result
                if converted_content.endswith('.html'):
                    # It's a file path to formatted HTML
                    content_type = 'html_file'
                    file_path = converted_content
                    pdf_content = None
                elif len(converted_content) > 100 and not converted_content.startswith('/'):
                    # It's base64 encoded PDF content
                    content_type = 'pdf'
                    file_path = None
                    pdf_content = converted_content
                else:
                    # It's base64 encoded HTML fallback
                    content_type = 'html'
                    file_path = None
                    pdf_content = None
            
            url = f"{self.device_id._get_base_url()}/print"
            
            # Prepare the final HTML content for printing
            final_html_content = html_content
            
            # For thermal printers (receipt, kitchen), use original HTML directly
            if self.printer_type in ['receipt', 'kitchen'] or 'cup' in self.name.lower():
                # Ensure HTML content is properly formatted for thermal printers
                if not html_content.strip().startswith('<!DOCTYPE') and not html_content.strip().startswith('<html'):
                    # Wrap HTML fragment with minimal structure
                    final_html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ margin: 0; padding: 2mm; font-family: Arial, sans-serif; font-size: 12px; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
            else:
                # For other printer types, use the converted content if available
                if content_type == 'html_file' and file_path:
                    # Read the formatted HTML file
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            final_html_content = f.read()
                        # Clean up the temporary file
                        os.unlink(file_path)
                    except Exception as e:
                        _logger.warning(f"Failed to read HTML file {file_path}: {e}")
                        # Fallback to original content
                        final_html_content = html_content
                elif content_type == 'pdf':
                    # For PDF content, we need to send it as HTML since the service expects html_content
                    # The service will handle the PDF conversion internally
                    final_html_content = html_content
            
            # Send only the fields expected by the virtual IoT service API
            payload = {
                'printer_id': printer_id,
                'layout_type': layout_type,
                'html_content': final_html_content,
                'source_model': 'virtual.iot.printer',
                'source_id': str(self.id)
            }
            
            # Debug logging to see what's actually being sent
            _logger.info(f"=== PRINT JOB DEBUG INFO ===")
            _logger.info(f"Printer ID: {printer_id}")
            _logger.info(f"Layout Type: {layout_type}")
            _logger.info(f"Original HTML Content Length: {len(html_content) if html_content else 0}")
            _logger.info(f"Final HTML Content Length: {len(final_html_content) if final_html_content else 0}")
            _logger.info(f"Final HTML Content Preview (first 200 chars): {final_html_content[:200] if final_html_content else 'EMPTY'}")
            _logger.info(f"URL: {url}")
            _logger.info(f"=== END DEBUG INFO ===")
            
            response = requests.post(
                url,
                json=payload,
                headers=self.device_id._get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print_job.write({
                    'status': 'success',
                    'response_data': str(result),
                    'completed_at': fields.Datetime.now()
                })
                self.status = 'ready'
                self.last_job_time = fields.Datetime.now()
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Print Job Sent'),
                        'message': _('Print job successfully sent to %s') % self.name,
                        'type': 'success',
                    }
                }
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                print_job.write({
                    'status': 'failed',
                    'error_message': error_msg,
                    'completed_at': fields.Datetime.now()
                })
                self.status = 'error'
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Print Job Failed'),
                        'message': _('Failed to send print job: %s') % error_msg,
                        'type': 'danger',
                    }
                }
                
        except Exception as e:
            error_msg = str(e)
            print_job.write({
                'status': 'failed',
                'error_message': error_msg,
                'completed_at': fields.Datetime.now()
            })
            self.status = 'error'
            _logger.error(f"Print job failed for printer {self.name}: {error_msg}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Print Job Failed'),
                    'message': _('Print job failed: %s') % error_msg,
                    'type': 'danger',
                }
            }
    
    @api.model
    def get_printers_by_type(self, printer_type):
        """Get all active printers of a specific type"""
        return self.search([
            ('printer_type', '=', printer_type),
            ('active', '=', True),
            ('device_id.status', '=', 'online')
        ])
    
    def name_get(self):
        """Custom name display"""
        result = []
        for printer in self:
            name = f"{printer.name} ({printer.device_id.name})"
            result.append((printer.id, name))
        return result