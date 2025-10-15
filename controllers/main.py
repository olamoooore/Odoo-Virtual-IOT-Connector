# -*- coding: utf-8 -*-

import json
import logging
from odoo import http, _
from odoo.http import request
from odoo.exceptions import ValidationError, AccessError

_logger = logging.getLogger(__name__)


class VirtualIoTController(http.Controller):
    
    def _authenticate_device(self, api_key):
        """Authenticate device using API key with enhanced security"""
        if not api_key:
            return None, "Missing API key"
        
        # Get client IP address
        ip_address = request.httprequest.environ.get('REMOTE_ADDR')
        if request.httprequest.environ.get('HTTP_X_FORWARDED_FOR'):
            ip_address = request.httprequest.environ.get('HTTP_X_FORWARDED_FOR').split(',')[0].strip()
        
        # Find device by API key (using hash comparison for security)
        devices = request.env['virtual.iot.device'].sudo().search([
            ('active', '=', True)
        ])
        
        device = None
        for dev in devices:
            if dev.verify_api_key(api_key):
                device = dev
                break
        
        if not device:
            return None, "Invalid API key"
        
        # Check if device is blocked
        if device.is_blocked():
            return None, f"Device blocked until {device.blocked_until}"
        
        # Check IP access
        if not device.check_ip_access(ip_address):
            device.record_failed_auth(ip_address)
            return None, f"IP address {ip_address} not allowed"
        
        # Check rate limiting
        if device.rate_limit_enabled:
            if not self._check_rate_limit(device, ip_address):
                return None, "Rate limit exceeded"
        
        # Record successful authentication
        device.record_successful_auth()
        
        return device, None
    
    def _get_api_key_from_request(self):
        """Extract API key from Authorization header"""
        auth_header = request.httprequest.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:]  # Remove 'Bearer ' prefix
        return None
    
    def _check_rate_limit(self, device, ip_address):
        """Check rate limiting for device"""
        # Simple in-memory rate limiting (in production, use Redis or database)
        cache_key = f"rate_limit_{device.id}_{ip_address}"
        
        # Get current minute timestamp
        import time
        current_minute = int(time.time() // 60)
        
        # For simplicity, we'll use a basic counter approach
        # In production, implement sliding window or token bucket
        request_count = request.session.get(f"{cache_key}_{current_minute}", 0)
        
        if request_count >= device.rate_limit_requests:
            return False
        
        request.session[f"{cache_key}_{current_minute}"] = request_count + 1
        return True
    
    def _json_response(self, data, status=200):
        """Return JSON response with proper headers"""
        response = request.make_response(
            json.dumps(data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Access-Control-Allow-Origin', '*'),
                ('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS'),
                ('Access-Control-Allow-Headers', 'Content-Type, Authorization')
            ]
        )
        response.status_code = status
        return response
    
    def _error_response(self, message, status=400):
        """Return error response"""
        return self._json_response({
            'error': True,
            'message': message
        }, status)
    
    @http.route('/virtual_iot/register', type='http', auth='public', methods=['POST'], csrf=False, cors='*')
    def register_device(self, **kwargs):
        """Register a new Virtual IoT device"""
        try:
            # Parse JSON data
            data = json.loads(request.httprequest.data.decode('utf-8'))
            
            # Validate required fields
            required_fields = ['name', 'ip', 'token']
            for field in required_fields:
                if field not in data:
                    return self._error_response(f"Missing required field: {field}")
            
            # Extract data
            name = data.get('name')
            ip_address = data.get('ip')
            port = data.get('port', 8000)
            api_key = data.get('token')
            
            # Register or update device
            device = request.env['virtual.iot.device'].sudo().register_device(
                name=name,
                ip_address=ip_address,
                port=port,
                api_key=api_key
            )
            
            _logger.info(f"Virtual IoT device registered: {name} ({ip_address}:{port})")
            
            return self._json_response({
                'success': True,
                'message': 'Device registered successfully',
                'device_id': device.id,
                'device_name': device.name
            })
            
        except json.JSONDecodeError:
            return self._error_response("Invalid JSON data")
        except Exception as e:
            _logger.error(f"Device registration failed: {str(e)}")
            return self._error_response(f"Registration failed: {str(e)}", 500)
    
    @http.route('/virtual_iot/devices', type='http', auth='none', methods=['GET'], csrf=False)
    def list_devices(self, **kwargs):
        """List all registered devices"""
        try:
            api_key = self._get_api_key_from_request()
            device, error = self._authenticate_device(api_key)
            if not device:
                return self._error_response(error or 'Unauthorized', 401)
            
            devices = request.env['virtual.iot.device'].sudo().search([
                ('active', '=', True)
            ])
            
            device_list = []
            for dev in devices:
                device_list.append({
                    'id': dev.id,
                    'name': dev.name,
                    'ip_address': dev.ip_address,
                    'port': dev.port,
                    'status': dev.status,
                    'last_seen': dev.last_seen,
                    'printer_count': len(dev.printer_ids),
                })
            
            return self._json_response({
                'success': True,
                'devices': device_list
            })
            
        except Exception as e:
            return self._error_response(str(e), 500)
    
    @http.route('/virtual_iot/device/<int:device_id>/status', type='http', auth='public', methods=['GET'], csrf=False, cors='*')
    def device_status(self, device_id, **kwargs):
        """Get device status"""
        try:
            api_key = self._get_api_key_from_request()
            device, error = self._authenticate_device(api_key)
            
            if not device:
                return self._error_response(error or "Unauthorized", 401)
            
            if device.id != device_id:
                return self._error_response("Unauthorized", 401)
            
            printers = []
            for printer in device.printer_ids:
                printers.append({
                    'id': printer.id,
                    'name': printer.name,
                    'type': printer.printer_type,
                    'status': printer.status,
                    'connection_type': printer.connection_type,
                    'device_path': printer.device_path,
                    'ip_address': printer.ip_address,
                    'port': printer.port,
                    'last_job_time': printer.last_job_time.isoformat() if printer.last_job_time else None
                })
            
            return self._json_response({
                'success': True,
                'device': {
                    'id': device.id,
                    'name': device.name,
                    'status': device.status,
                    'last_seen': device.last_seen.isoformat() if device.last_seen else None,
                    'printers': printers
                }
            })
            
        except Exception as e:
            _logger.error(f"Failed to get device status: {str(e)}")
            return self._error_response(f"Failed to get device status: {str(e)}", 500)
    
    @http.route('/virtual_iot/device/<int:device_id>/printers', type='http', auth='public', methods=['GET'], csrf=False, cors='*')
    def device_printers(self, device_id, **kwargs):
        """Get device printers"""
        try:
            api_key = self._get_api_key_from_request()
            device, error = self._authenticate_device(api_key)
            
            if not device:
                return self._error_response(error or "Unauthorized", 401)
            
            if device.id != device_id:
                return self._error_response("Unauthorized", 401)
            
            printers = []
            for printer in device.printer_ids.filtered(lambda p: p.active):
                printers.append({
                    'id': printer.id,
                    'name': printer.name,
                    'type': printer.printer_type,
                    'status': printer.status,
                    'connection_type': printer.connection_type,
                    'device_path': printer.device_path,
                    'ip_address': printer.ip_address,
                    'port': printer.port,
                    'paper_width': printer.paper_width,
                    'paper_height': printer.paper_height,
                    'dpi': printer.dpi
                })
            
            return self._json_response({
                'success': True,
                'printers': printers
            })
            
        except Exception as e:
            _logger.error(f"Failed to get device printers: {str(e)}")
            return self._error_response(f"Failed to get device printers: {str(e)}", 500)
    
    @http.route('/virtual_iot/print', type='http', auth='public', methods=['POST'], csrf=False, cors='*')
    def print_job(self, **kwargs):
        """Receive print job from Virtual IoT service"""
        try:
            # Parse JSON data
            data = json.loads(request.httprequest.data.decode('utf-8'))
            
            # Validate required fields
            required_fields = ['device_id', 'printer_name', 'html_content']
            for field in required_fields:
                if field not in data:
                    return self._error_response(f"Missing required field: {field}")
            
            # Authenticate device
            api_key = self._get_api_key_from_request()
            device, error = self._authenticate_device(api_key)
            
            if not device:
                return self._error_response(error or "Unauthorized", 401)
            
            if device.id != data.get('device_id'):
                return self._error_response("Unauthorized", 401)
            
            # Find printer
            printer = request.env['virtual.iot.printer'].sudo().search([
                ('device_id', '=', device.id),
                ('name', '=', data.get('printer_name')),
                ('active', '=', True)
            ], limit=1)
            
            if not printer:
                return self._error_response("Printer not found")
            
            # Create print job
            job_name = data.get('job_reference')
            if not job_name:
                sequence = request.env['ir.sequence'].next_by_code("virtual.iot.print.job")
                job_name = f'Job-{sequence}'
            
            print_job = request.env['virtual.iot.print.job'].sudo().create({
                'name': job_name,
                'device_id': device.id,
                'printer_id': printer.id,
                'html_content': data.get('html_content'),
                'layout_type': data.get('layout_type', 'receipt'),
                'status': data.get('status', 'success'),
                'response_data': json.dumps(data.get('response_data', {})),
                'source_model': data.get('source_model'),
                'source_id': data.get('source_id')
            })
            
            if data.get('status') == 'success':
                print_job.completed_at = request.env.cr.now()
                printer.last_job_time = request.env.cr.now()
                printer.status = 'ready'
            elif data.get('status') == 'failed':
                print_job.error_message = data.get('error_message', 'Unknown error')
                print_job.completed_at = request.env.cr.now()
                printer.status = 'error'
            
            # Update device status
            device.status = 'online'
            device.last_seen = request.env.cr.now()
            
            _logger.info(f"Print job received: {print_job.name} for printer {printer.name}")
            
            return self._json_response({
                'success': True,
                'message': 'Print job recorded successfully',
                'job_id': print_job.id
            })
            
        except json.JSONDecodeError:
            return self._error_response("Invalid JSON data")
        except Exception as e:
            _logger.error(f"Print job recording failed: {str(e)}")
            return self._error_response(f"Print job recording failed: {str(e)}", 500)
    
    @http.route('/virtual_iot/pos_print', type='json', auth='user', methods=['POST'], csrf=False)
    def pos_print_job(self, **kwargs):
        """Receive print job from POS frontend"""
        try:
            # Get data from kwargs (JSON RPC format)
            data = kwargs
            
            # Debug logging
            _logger.info(f"🔍 POS Print Job Debug - Received data keys: {list(data.keys())}")
            _logger.info(f"🔍 html_content type: {type(data.get('html_content'))}")
            _logger.info(f"🔍 html_content length: {len(str(data.get('html_content', '')))}")
            _logger.info(f"🔍 html_content preview: {str(data.get('html_content', ''))[:200]}...")
            
            # Validate required fields
            required_fields = ['device_id', 'printer_name']
            for field in required_fields:
                if field not in data:
                    return {'success': False, 'error': f"Missing required field: {field}"}
            
            # Check if we have either html_content or qweb_template
            html_content = data.get('html_content')
            if not html_content and not data.get('qweb_template'):
                return {'success': False, 'error': "Either 'html_content' or 'qweb_template' is required"}
            
            # Additional validation for html_content
            if html_content and (len(str(html_content).strip()) < 10 or str(html_content).strip() in ['comment', 'undefined', 'null']):
                return {'success': False, 'error': f"Invalid html_content received: '{html_content}'. Content appears to be empty or invalid."}
            
            # Get device (no API key needed for authenticated users)
            device = request.env['virtual.iot.device'].search([
                ('id', '=', data.get('device_id')),
                ('active', '=', True)
            ], limit=1)
            
            if not device:
                return {'success': False, 'error': "Device not found"}
            
            # Find printer
            printer = request.env['virtual.iot.printer'].search([
                ('device_id', '=', device.id),
                ('name', '=', data.get('printer_name')),
                ('active', '=', True)
            ], limit=1)
            
            if not printer:
                return {'success': False, 'error': "Printer not found"}
            
            # Process content (QWeb template or HTML)
            html_content = data.get('html_content')
            
            # If QWeb template is provided, process it
            if data.get('qweb_template'):
                qweb_processor = request.env['virtual.iot.qweb.processor']
                context_data = data.get('context_data', {})
                
                _logger.info(f"Processing QWeb template for printer {printer.name}")
                
                result = qweb_processor.process_qweb_template(
                    data.get('qweb_template'),
                    context_data
                )
                
                if not result['success']:
                    _logger.error(f"QWeb processing failed: {result['error']}")
                    return {'success': False, 'error': f"QWeb processing failed: {result['error']}"}
                
                html_content = result['content']
                _logger.info(f"QWeb template processed successfully for printer {printer.name}")
            
            # Ensure we have HTML content
            if not html_content:
                return {'success': False, 'error': "No HTML content to print"}
            
            # Create print job
            job_name = data.get('job_reference')
            if not job_name:
                sequence = request.env['ir.sequence'].next_by_code("virtual.iot.print.job")
                job_name = f'Job-{sequence}'
            
            print_job = request.env['virtual.iot.print.job'].create({
                'name': job_name,
                'device_id': device.id,
                'printer_id': printer.id,
                'html_content': html_content,  # Use processed HTML content
                'layout_type': data.get('layout_type', 'receipt'),
                'status': 'pending',  # Start as pending
                'response_data': json.dumps(data.get('response_data', {})),
                'source_model': data.get('source_model'),
                'source_id': data.get('source_id')
            })
            
            _logger.info(f"POS print job created: {print_job.name} for printer {printer.name}")
            
            # Actually send the print job to the Virtual IoT service
            try:
                result = printer.send_print_job(
                    html_content=html_content,  # Use processed HTML content
                    layout_type=data.get('layout_type', 'receipt'),
                    source_model=data.get('source_model'),
                    source_id=data.get('source_id')
                )
                
                # Update print job status based on result
                print_job.status = 'success'
                print_job.completed_at = request.env.cr.now()
                printer.last_job_time = request.env.cr.now()
                printer.status = 'ready'
                device.status = 'online'
                device.last_seen = request.env.cr.now()
                
                _logger.info(f"POS print job sent successfully: {print_job.name}")
                
                return {
                    'success': True,
                    'message': 'Print job sent successfully',
                    'job_id': print_job.id
                }
                
            except Exception as print_error:
                # Update print job status to failed
                print_job.status = 'failed'
                print_job.error_message = str(print_error)
                print_job.completed_at = request.env.cr.now()
                printer.status = 'error'
                
                _logger.error(f"POS print job failed: {print_job.name} - {str(print_error)}")
                
                return {
                    'success': False,
                    'error': f"Print job failed: {str(print_error)}",
                    'job_id': print_job.id
                }
            
        except Exception as e:
            _logger.error(f"POS print job recording failed: {str(e)}")
            return {'success': False, 'error': f"Print job recording failed: {str(e)}"}
    
    @http.route('/virtual_iot/jobs', type='http', auth='public', methods=['GET'], csrf=False, cors='*')
    def list_print_jobs(self, **kwargs):
        """List print jobs with optional filtering"""
        try:
            api_key = self._get_api_key_from_request()
            device, error = self._authenticate_device(api_key)
            
            if not device:
                return self._error_response(error or "Unauthorized", 401)
            
            # Parse query parameters
            device_id = kwargs.get('device_id')
            printer_id = kwargs.get('printer_id')
            status = kwargs.get('status')
            limit = int(kwargs.get('limit', 50))
            offset = int(kwargs.get('offset', 0))
            
            # Build domain
            domain = []
            if device_id:
                domain.append(('device_id', '=', int(device_id)))
            if printer_id:
                domain.append(('printer_id', '=', int(printer_id)))
            if status:
                domain.append(('status', '=', status))
            
            # Search jobs
            jobs = request.env['virtual.iot.print.job'].search(
                domain, 
                limit=limit, 
                offset=offset, 
                order='create_date desc'
            )
            
            job_list = []
            for job in jobs:
                job_list.append({
                    'id': job.id,
                    'name': job.name,
                    'device_name': job.device_name,
                    'printer_name': job.printer_name,
                    'printer_type': job.printer_type,
                    'status': job.status,
                    'layout_type': job.layout_type,
                    'created_at': job.created_at.isoformat() if job.created_at else None,
                    'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                    'duration': job.duration,
                    'user_id': job.user_id.name if job.user_id else None
                })
            
            return self._json_response({
                'success': True,
                'jobs': job_list,
                'total': len(jobs)
            })
            
        except Exception as e:
            _logger.error(f"Failed to list print jobs: {str(e)}")
            return self._error_response(f"Failed to list print jobs: {str(e)}", 500)
    
    @http.route('/virtual_iot/statistics', type='http', auth='public', methods=['GET'], csrf=False, cors='*')
    def get_statistics(self, **kwargs):
        """Get system statistics"""
        try:
            api_key = self._get_api_key_from_request()
            device, error = self._authenticate_device(api_key)
            
            if not device:
                return self._error_response(error or "Unauthorized", 401)
            # Device statistics
            devices = request.env['virtual.iot.device'].search([('active', '=', True)])
            device_stats = {
                'total': len(devices),
                'online': len(devices.filtered(lambda d: d.status == 'online')),
                'offline': len(devices.filtered(lambda d: d.status == 'offline')),
                'error': len(devices.filtered(lambda d: d.status == 'error'))
            }
            
            # Printer statistics
            printers = request.env['virtual.iot.printer'].search([('active', '=', True)])
            printer_stats = {
                'total': len(printers),
                'ready': len(printers.filtered(lambda p: p.status == 'ready')),
                'busy': len(printers.filtered(lambda p: p.status == 'busy')),
                'offline': len(printers.filtered(lambda p: p.status == 'offline')),
                'error': len(printers.filtered(lambda p: p.status == 'error'))
            }
            
            # Print job statistics
            job_stats = request.env['virtual.iot.print.job'].get_statistics()
            
            return self._json_response({
                'success': True,
                'statistics': {
                    'devices': device_stats,
                    'printers': printer_stats,
                    'print_jobs': job_stats
                }
            })
            
        except Exception as e:
            _logger.error(f"Failed to get statistics: {str(e)}")
            return self._error_response(f"Failed to get statistics: {str(e)}", 500)
    
    @http.route('/virtual_iot/health', type='http', auth='public', methods=['GET'], csrf=False, cors='*')
    def health_check(self, **kwargs):
        """Health check endpoint"""
        return self._json_response({
            'success': True,
            'status': 'healthy',
            'timestamp': request.env.cr.now().isoformat(),
            'version': '1.0.0'
        })