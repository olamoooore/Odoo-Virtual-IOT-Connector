# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class VirtualIoTDashboardController(http.Controller):

    @http.route('/virtual_iot/dashboard/test', type='http', auth='user', methods=['GET'])
    def test_dashboard(self):
        """Test endpoint to verify dashboard functionality"""
        _logger.info("=== DASHBOARD CONTROLLER: Test endpoint called ===")
        
        try:
            # Test database access
            devices = request.env['virtual.iot.device'].search([('active', '=', True)])
            printers = request.env['virtual.iot.printer'].search([('active', '=', True)])
            print_jobs = request.env['virtual.iot.print.job'].search([], limit=10, order='created_date desc')
            
            _logger.info(f"=== DASHBOARD CONTROLLER: Found {len(devices)} devices, {len(printers)} printers, {len(print_jobs)} print jobs ===")
            
            result = {
                'status': 'success',
                'data': {
                    'device_count': len(devices),
                    'printer_count': len(printers),
                    'print_job_count': len(print_jobs),
                    'devices': [{'id': d.id, 'name': d.name, 'status': d.status} for d in devices],
                    'printers': [{'id': p.id, 'name': p.name, 'status': p.status} for p in printers],
                }
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            _logger.error(f"=== DASHBOARD CONTROLLER ERROR: {str(e)} ===")
            return json.dumps({'status': 'error', 'message': str(e)}, indent=2)

    @http.route('/virtual_iot/dashboard/data', type='json', auth='user', methods=['POST'])
    def get_dashboard_data(self):
        """JSON endpoint for dashboard data - matches the ORM calls from JavaScript"""
        _logger.info("=== DASHBOARD CONTROLLER: JSON endpoint called ===")
        
        try:
            # Simulate the exact same calls as JavaScript
            devices = request.env['virtual.iot.device'].search_read(
                [('active', '=', True)],
                ['id', 'name', 'device_type', 'status', 'last_seen']
            )
            
            printers = request.env['virtual.iot.printer'].search_read(
                [('active', '=', True)],
                ['id', 'name', 'printer_type', 'status', 'last_seen']
            )
            
            print_jobs = request.env['virtual.iot.print.job'].search_read(
                [],
                ['id', 'name', 'status', 'created_date', 'printer_id'],
                limit=10, order='created_date desc'
            )
            
            _logger.info(f"=== DASHBOARD CONTROLLER JSON: Found {len(devices)} devices, {len(printers)} printers, {len(print_jobs)} print jobs ===")
            
            return {
                'devices': devices,
                'printers': printers,
                'print_jobs': print_jobs,
                'statistics': {
                    'deviceCount': len(devices),
                    'printerCount': len(printers),
                    'pendingJobs': len([j for j in print_jobs if j.get('status') == 'pending'])
                }
            }
            
        except Exception as e:
            _logger.error(f"=== DASHBOARD CONTROLLER JSON ERROR: {str(e)} ===")
            raise