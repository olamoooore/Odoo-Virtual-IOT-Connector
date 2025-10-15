/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

class VirtualIoTDashboard extends Component {
    setup() {
        console.log('=== DASHBOARD COMPONENT: Setup called ===');
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        
        this.state = useState({
            devices: [],
            printers: [],
            recentPrintJobs: [],
            statistics: {
                deviceCount: 0,
                printerCount: 0,
                pendingJobs: 0
            },
            loading: true
        });

        console.log('=== DASHBOARD COMPONENT: Initial state set ===');
        
        onMounted(() => {
            console.log('=== DASHBOARD COMPONENT: onMounted called ===');
            this.loadDashboardData();
            // Set up refresh interval
            this.state.refreshInterval = setInterval(() => {
                this.loadDashboardData();
            }, 30000);
        });

        onWillUnmount(() => {
            if (this.state.refreshInterval) {
                clearInterval(this.state.refreshInterval);
            }
        });
    }

    async loadDashboardData() {
        console.log('=== DASHBOARD: Starting loadDashboardData ===');
        // Fixed field references - v2
        
        try {
            this.state.loading = true;
            
            // Load devices with explicit active filter
            console.log('=== DASHBOARD: Loading devices ===');
            const devices = await this.orm.searchRead(
                'virtual.iot.device',
                [['active', '=', true]],
                ['id', 'name', 'status', 'last_seen']
            );
            console.log('=== DASHBOARD: Devices loaded:', devices.length, devices);

            // Load printers with explicit active filter  
            console.log('=== DASHBOARD: Loading printers ===');
            const printers = await this.orm.searchRead(
                'virtual.iot.printer',
                [['active', '=', true]],
                ['id', 'name', 'printer_type', 'status', 'last_job_time']
            );
            console.log('=== DASHBOARD: Printers loaded:', printers.length, printers);

            // Load recent print jobs
            console.log('=== DASHBOARD: Loading print jobs ===');
            const printJobs = await this.orm.searchRead(
                'virtual.iot.print.job',
                [],
                ['id', 'name', 'status', 'created_at', 'printer_id'],
                { limit: 10, order: 'created_at desc' }
            );
            console.log('=== DASHBOARD: Print jobs loaded:', printJobs.length, printJobs);

            // Calculate statistics
            console.log('=== DASHBOARD: Calculating statistics ===');
            const deviceCount = devices.length;
            const printerCount = printers.length;
            const pendingJobs = printJobs.filter(job => job.status === 'pending').length;
            
            console.log('=== DASHBOARD: Device count:', deviceCount);
            console.log('=== DASHBOARD: Printer count:', printerCount);
            console.log('=== DASHBOARD: Pending jobs:', pendingJobs);

            // Update state
            console.log('=== DASHBOARD: Updating state ===');
            this.state.devices = devices;
            this.state.printers = printers;
            this.state.recentPrintJobs = printJobs;
            this.state.statistics = {
                deviceCount,
                printerCount,
                pendingJobs
            };
            
            console.log('=== DASHBOARD: Final state:', this.state);
            console.log('=== DASHBOARD: loadDashboardData completed ===');
            
        } catch (error) {
            console.error('=== DASHBOARD ERROR: Failed to load dashboard data:', error);
        } finally {
            this.state.loading = false;
        }
    }

    async testDeviceConnection(deviceId) {
        try {
            await this.orm.call('virtual.iot.device', 'test_connection', [deviceId]);
            this.notification.add("Device connection test successful", { type: "success" });
        } catch (error) {
            console.error("Error testing connection:", error);
            this.notification.add("Error testing device connection", { type: "danger" });
        }
    }

    async syncDevicePrinters(deviceId) {
        try {
            await this.orm.call('virtual.iot.device', 'sync_printers', [deviceId]);
            this.notification.add("Printers synchronized successfully", { type: "success" });
            await this.loadDashboardData();
        } catch (error) {
            console.error("Error syncing printers:", error);
            this.notification.add("Error synchronizing printers", { type: "danger" });
        }
    }

    openDeviceForm(deviceId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'virtual.iot.device',
            res_id: deviceId,
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'current',
        });
    }

    openPrinterForm(printerId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'virtual.iot.printer',
            res_id: printerId,
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'current',
        });
    }

    openDevicesList() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'virtual.iot.device',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    openPrintersList() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'virtual.iot.printer',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    openPrintJobsList() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'virtual.iot.print.job',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    // Convenience methods for template
    openDevices() {
        this.openDevicesList();
    }

    openPrinters() {
        this.openPrintersList();
    }

    openPrintJobs() {
        this.openPrintJobsList();
    }

    getStatusBadgeClass(status) {
        const statusClasses = {
            'online': 'badge-success',
            'offline': 'badge-secondary',
            'error': 'badge-danger',
            'ready': 'badge-success',
            'busy': 'badge-warning',
            'success': 'badge-success',
            'failed': 'badge-danger',
            'pending': 'badge-info',
            'processing': 'badge-warning'
        };
        return statusClasses[status] || 'badge-secondary';
    }

    formatDateTime(dateTime) {
        if (!dateTime) return 'Never';
        return new Date(dateTime).toLocaleString();
    }
}

VirtualIoTDashboard.template = "virtual_iot_connector.DashboardTemplate";

registry.category("actions").add("virtual_iot_dashboard", VirtualIoTDashboard);