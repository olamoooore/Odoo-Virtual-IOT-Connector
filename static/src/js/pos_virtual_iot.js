/** @odoo-module **/

import { registry } from "@web/core/registry";
import { PrinterService } from "@point_of_sale/app/printer/printer_service";
import { PosPrinterService } from "@point_of_sale/app/printer/pos_printer_service";
import { rpc } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";

// Patch the PosPrinterService to handle virtual IoT printing
patch(PosPrinterService.prototype, {
    async print(component, props, options) {
        try {
            // Get POS service through the service registry
            let posStore = null;
            let config = null;
            
            // Try to get POS store from the service registry
            if (this.env?.services?.pos) {
                posStore = this.env.services.pos;
                config = posStore.config;
            } else {
                // Try to get from global registry
                const services = window.odoo?.env?.services;
                if (services?.pos) {
                    posStore = services.pos;
                    config = posStore.config;
                } else {
                    // Fallback: Use RPC to get config when POS service is not available
                    const configId = window.odoo?.pos_config_id;
                    if (configId) {
                        try {
                            // Make RPC call to get the POS config
                            config = await rpc('/web/dataset/call_kw', {
                                model: 'pos.config',
                                method: 'read',
                                args: [[configId], ['use_virtual_iot', 'virtual_iot_device_id']],
                                kwargs: {}
                            });
                            if (config && config.length > 0) {
                                config = config[0]; // Get the first (and only) result
                            } else {
                                config = null;
                            }
                        } catch (error) {
                            config = null;
                        }
                    }
                }
            }
            
            // Check if Virtual IoT is enabled
            if (config?.use_virtual_iot && config?.virtual_iot_device_id) {
                return await this.printVirtualIoT(component, props, options);
            } else {
                return await super.print(component, props, options);
            }
        } catch (error) {
            // Fallback to original print method
            return await super.print(component, props, options);
        }
    },

    async printVirtualIoT(component, props, options) {
        this.state.isPrinting = true;
        
        try {
            // Get current POS config ID
            let configId = null;
            
            // Try to get POS config from the service
            if (this.env?.services?.pos) {
                configId = this.env.services.pos.config?.id;
            } else {
                // Try to get from global registry
                const services = window.odoo?.env?.services;
                if (services?.pos) {
                    configId = services.pos.config?.id;
                } else {
                    // Fallback: Use global pos_config_id
                    configId = window.odoo?.pos_config_id;
                }
            }
            
            if (!configId) {
                throw new Error('Could not determine current POS config ID');
            }
            
            // Render component to HTML
            const toHtmlResult = this.renderer.toHtml(component, props);
            let domElement;
            if (toHtmlResult && typeof toHtmlResult.then === 'function') {
                domElement = await toHtmlResult;
            } else {
                domElement = toHtmlResult;
            }
            
            if (!domElement) {
                throw new Error('Failed to render component to DOM element');
            }
            
            // Handle case where toHtml returns a string instead of DOM element
            let actualElement = domElement;
            if (typeof domElement === 'string') {
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = domElement;
                actualElement = tempDiv.firstElementChild || tempDiv;
            } else if (domElement && domElement.nodeType === Node.COMMENT_NODE) {
                // Try to re-render the component to bypass the comment
                try {
                    const reRenderResult = this.renderer.toHtml(component, props);
                    if (reRenderResult && typeof reRenderResult.then === 'function') {
                        actualElement = await reRenderResult;
                    } else {
                        actualElement = reRenderResult;
                    }
                } catch (reRenderError) {
                    // Re-rendering failed, search DOM instead
                }
                
                // If re-rendering didn't work, search the document for the receipt element
                if (!actualElement || actualElement.nodeType === Node.COMMENT_NODE) {
                    actualElement = document.querySelector('.pos-receipt');
                }
            }
            
            // Extract CSS styles for the receipt
            const cssStyles = this.extractCSSForElement(actualElement);
            
            // Convert DOM element to HTML string and wrap with styles
            let elementHTML;
            if (typeof domElement === 'string') {
                elementHTML = domElement;
            } else if (actualElement && actualElement.nodeType === Node.ELEMENT_NODE && actualElement.outerHTML) {
                elementHTML = actualElement.outerHTML;
            } else if (actualElement && actualElement.nodeType === Node.ELEMENT_NODE && actualElement.innerHTML) {
                elementHTML = actualElement.innerHTML;
            } else if (actualElement && actualElement.outerHTML) {
                elementHTML = actualElement.outerHTML;
            } else if (actualElement && actualElement.innerHTML) {
                elementHTML = actualElement.innerHTML;
            } else if (typeof domElement === 'object' && domElement.outerHTML) {
                elementHTML = domElement.outerHTML;
            } else if (typeof domElement === 'object' && domElement.innerHTML) {
                elementHTML = domElement.innerHTML;
            } else {
                // Final fallback - create a basic receipt structure
                elementHTML = '<div class="pos-receipt"><p>Receipt content could not be rendered</p></div>';
            }
            
            const htmlContent = `
                <html>
                <head>
                    <style>
                        ${cssStyles}
                    </style>
                </head>
                <body>
                    ${elementHTML}
                </body>
                </html>
            `;
            
            // Get POS config using the current config ID
            const config = await rpc('/web/dataset/call_kw', {
                model: 'pos.config',
                method: 'read',
                args: [[configId], ['use_virtual_iot', 'virtual_iot_device_id', 'virtual_receipt_printer_id']],
                kwargs: {}
            });
            
            if (!config || !config[0] || !config[0].use_virtual_iot) {
                throw new Error('Virtual IoT not enabled for this POS config');
            }
            
            const posConfig = config[0];
            
            // Skip image conversion
            const imageData = null;
            
            // Prepare print data
            const printData = {
                device_id: posConfig.virtual_iot_device_id[0],
                printer_name: posConfig.virtual_receipt_printer_id ? posConfig.virtual_receipt_printer_id[1] : 'Receipt Printer',
                html_content: htmlContent,
                layout_type: 'receipt',
                status: 'success',
                job_reference: `POS-${Date.now()}`,
                source_model: 'pos.order',
                response_data: {
                    image_data: imageData,
                    options: options || {}
                }
            };
            
            const result = await rpc('/virtual_iot/pos_print', printData);
            
            return true;
            
        } catch (error) {
            console.error('❌ Virtual IoT printing failed:', error);
            window.virtualIoTDebug.errors.push({
                error: error.message,
                timestamp: new Date().toISOString(),
                stack: error.stack
            });
            return false;
        } finally {
            this.state.isPrinting = false;
        }
    },

    extractCSSForElement(element) {
        if (!element) {
            return this.getFallbackCSS();
        }
        
        const relevantRules = [];
        const processedSelectors = new Set();
        
        try {
            // Get all stylesheets
            const stylesheets = Array.from(document.styleSheets);
            
            for (const stylesheet of stylesheets) {
                try {
                    // Skip external stylesheets that might cause CORS issues
                    if (stylesheet.href && !stylesheet.href.startsWith(window.location.origin)) {
                        continue;
                    }
                    
                    const rules = Array.from(stylesheet.cssRules || stylesheet.rules || []);
                    
                    for (const rule of rules) {
                        if (rule.type === CSSRule.STYLE_RULE) {
                            const selector = rule.selectorText;
                            
                            // Skip if we've already processed this selector
                            if (processedSelectors.has(selector)) {
                                continue;
                            }
                            
                            try {
                                // Check if this rule applies to our element or its children
                                if (element.matches && (element.matches(selector) || element.querySelector(selector))) {
                                    relevantRules.push(rule.cssText);
                                    processedSelectors.add(selector);
                                }
                            } catch (e) {
                                // Invalid selector, skip it
                                continue;
                            }
                        }
                    }
                } catch (e) {
                    // Could not access stylesheet rules
                    continue;
                }
            }
            
            // Add some common POS receipt styles as fallback
            const fallbackStyles = `
                .pos-receipt {
                    font-family: 'Lucida Console', Monaco, monospace;
                    font-size: 12px;
                    line-height: 1.2;
                    color: #000;
                    background: #fff;
                    padding: 10px;
                    max-width: 300px;
                    margin: 0 auto;
                }
                .pos-receipt .receipt-header {
                    text-align: center;
                    margin-bottom: 10px;
                    font-weight: bold;
                }
                .pos-receipt .receipt-orderlines {
                    margin: 10px 0;
                }
                .pos-receipt .receipt-line {
                    display: flex;
                    justify-content: space-between;
                    margin: 2px 0;
                }
                .pos-receipt .receipt-total {
                    border-top: 1px solid #000;
                    margin-top: 10px;
                    padding-top: 5px;
                    font-weight: bold;
                }
                .pos-receipt .receipt-footer {
                    text-align: center;
                    margin-top: 10px;
                    font-size: 10px;
                }
            `;
            
            return relevantRules.join('\n') + '\n' + fallbackStyles;
            
        } catch (error) {
            // Return basic fallback styles
            return `
                .pos-receipt {
                    font-family: 'Lucida Console', Monaco, monospace;
                    font-size: 12px;
                    line-height: 1.2;
                    color: #000;
                    background: #fff;
                    padding: 10px;
                    max-width: 300px;
                    margin: 0 auto;
                }
            `;
        }
    },

    getFallbackCSS() {
        return `
            .pos-receipt {
                font-family: 'Lucida Console', Monaco, monospace;
                font-size: 12px;
                line-height: 1.2;
                color: #000;
                background: #fff;
                padding: 10px;
                max-width: 300px;
                margin: 0 auto;
            }
            .pos-receipt .receipt-line {
                display: flex;
                justify-content: space-between;
                margin: 2px 0;
            }
            .pos-receipt .receipt-total {
                border-top: 1px solid #000;
                margin-top: 10px;
                padding-top: 5px;
                font-weight: bold;
            }
            .pos-receipt .receipt-footer {
                text-align: center;
                margin-top: 10px;
                font-size: 10px;
            }
        `;
    },

    async loadAllImagesVirtualIoT(element) {
        console.log('Loading images for virtual IoT');
        const images = element.querySelectorAll('img');
        const promises = [];
        
        for (const img of images) {
            if (img.src && !img.complete) {
                promises.push(new Promise((resolve) => {
                    img.onload = resolve;
                    img.onerror = resolve; // Resolve even on error to not block
                }));
            }
        }
        
        if (promises.length > 0) {
            await Promise.all(promises);
        }
        console.log(`Loaded ${promises.length} images for virtual IoT`);
    },

    async convertToImageData(element) {
        console.log('Converting to image data for virtual IoT');
        
        // Try html2canvas if available
        if (window.html2canvas) {
            try {
                const canvas = await window.html2canvas(element, {
                    backgroundColor: '#ffffff',
                    scale: 2,
                    useCORS: true
                });
                return canvas.toDataURL('image/png');
            } catch (error) {
                console.warn('html2canvas failed, using fallback:', error);
            }
        }
        
        // Fallback: create SVG representation
        const svgData = `
            <svg xmlns="http://www.w3.org/2000/svg" width="400" height="600">
                <foreignObject width="100%" height="100%">
                    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: monospace; font-size: 12px; padding: 10px;">
                        ${element.innerHTML}
                    </div>
                </foreignObject>
            </svg>
        `;
        
        return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement('canvas');
                canvas.width = 400;
                canvas.height = 600;
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = '#ffffff';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(img, 0, 0);
                resolve(canvas.toDataURL('image/png'));
            };
            img.onerror = () => {
                // Ultimate fallback - return a simple base64 image
                resolve('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==');
            };
            const url = 'data:image/svg+xml;base64,' + btoa(svgData);
            img.src = url;
        });
    }
});

// Also patch the base PrinterService to catch any print attempts
patch(PrinterService.prototype, {
    async print(component, props, options) {
        return super.print(component, props, options);
    }
});