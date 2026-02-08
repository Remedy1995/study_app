// Enhanced PDF Generation with Progress Tracking
class PDFGenerator {
    constructor() {
        this.websocket = null;
        this.currentLectureId = null;
    }

    // Initialize WebSocket connection for real-time progress
    initWebSocket(lectureId) {
        this.currentLectureId = lectureId;
        
        const wsUrl = `ws://13.218.104.234:8002/ws/lecture/${lectureId}/`;
        this.websocket = new WebSocket(wsUrl);
        
        this.websocket.onopen = () => {
            console.log('PDF Progress WebSocket connected');
        };
        
        this.websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleProgressUpdate(data);
        };
        
        this.websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
        
        this.websocket.onclose = () => {
            console.log('WebSocket disconnected');
        };
    }

    // Handle progress updates from backend
    handleProgressUpdate(data) {
        const progressBar = document.getElementById('pdf-progress');
        const statusText = document.getElementById('pdf-status');
        const downloadBtn = document.getElementById('download-pdf-btn');
        
        if (!progressBar || !statusText) return;
        
        switch(data.status) {
            case 'Exporting PDF':
                this.updateProgress(10, 'Starting PDF generation...');
                break;
                
            case 'Creating PDF layout':
                this.updateProgress(30, 'Creating PDF layout...');
                break;
                
            case 'Adding content to PDF':
                this.updateProgress(60, 'Adding content to PDF...');
                break;
                
            case 'Saving PDF file':
                this.updateProgress(90, 'Saving PDF file...');
                break;
                
            case 'PDF ready':
                this.updateProgress(100, 'PDF ready for download!');
                if (downloadBtn && data.pdf) {
                    downloadBtn.href = data.pdf;
                    downloadBtn.style.display = 'block';
                    downloadBtn.classList.remove('disabled');
                }
                this.closeWebSocket();
                break;
                
            case 'Error':
                this.updateProgress(0, `Error: ${data.message || 'Unknown error'}`);
                this.showError(data.message);
                this.closeWebSocket();
                break;
        }
    }

    // Update progress bar and status
    updateProgress(percentage, message) {
        const progressBar = document.getElementById('pdf-progress');
        const statusText = document.getElementById('pdf-status');
        
        if (progressBar) {
            progressBar.style.width = `${percentage}%`;
            progressBar.setAttribute('aria-valuenow', percentage);
        }
        
        if (statusText) {
            statusText.textContent = message;
        }
        
        // Add animation
        if (progressBar) {
            progressBar.classList.add('progress-animated');
            setTimeout(() => {
                progressBar.classList.remove('progress-animated');
            }, 300);
        }
    }

    // Show error message
    showError(message) {
        const errorDiv = document.getElementById('pdf-error');
        if (errorDiv) {
            errorDiv.textContent = message;
            errorDiv.style.display = 'block';
            setTimeout(() => {
                errorDiv.style.display = 'none';
            }, 5000);
        }
    }

    // Close WebSocket connection
    closeWebSocket() {
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }
    }

    // Generate PDF with enhanced UX
    async generatePDF(lectureId, authToken) {
        // Show loading UI
        this.showLoadingUI();
        
        // Initialize WebSocket for progress tracking
        this.initWebSocket(lectureId);
        
        try {
            const response = await fetch(`http://13.218.104.234/api/lectures/${lectureId}/export_pdf/`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${authToken}`,
                    'Content-Type': 'application/json',
                },
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const result = await response.json();
            console.log('PDF generation started:', result);
            
        } catch (error) {
            console.error('Error starting PDF generation:', error);
            this.showError('Failed to start PDF generation');
            this.closeWebSocket();
        }
    }

    // Show loading UI elements
    showLoadingUI() {
        const progressBar = document.getElementById('pdf-progress');
        const statusText = document.getElementById('pdf-status');
        const downloadBtn = document.getElementById('download-pdf-btn');
        const loadingDiv = document.getElementById('pdf-loading');
        
        if (loadingDiv) loadingDiv.style.display = 'block';
        if (progressBar) {
            progressBar.style.width = '0%';
            progressBar.style.display = 'block';
        }
        if (statusText) {
            statusText.textContent = 'Initializing...';
            statusText.style.display = 'block';
        }
        if (downloadBtn) {
            downloadBtn.style.display = 'none';
            downloadBtn.classList.add('disabled');
        }
    }
}

// CSS for enhanced progress tracking
const progressStyles = `
<style>
.pdf-progress-container {
    margin: 20px 0;
    padding: 15px;
    border: 1px solid #ddd;
    border-radius: 8px;
    background: #f8f9fa;
}

.progress {
    height: 20px;
    background-color: #e9ecef;
    border-radius: 10px;
    overflow: hidden;
    margin: 10px 0;
}

.progress-bar {
    height: 100%;
    background: linear-gradient(90deg, #007bff, #0056b3);
    transition: width 0.3s ease;
    border-radius: 10px;
}

.progress-animated {
    animation: progress-pulse 0.3s ease-in-out;
}

@keyframes progress-pulse {
    0% { opacity: 0.7; }
    50% { opacity: 1; }
    100% { opacity: 0.7; }
}

.pdf-status {
    font-weight: 600;
    color: #495057;
    margin: 10px 0;
}

.pdf-error {
    color: #dc3545;
    background: #f8d7da;
    padding: 10px;
    border-radius: 5px;
    margin: 10px 0;
    display: none;
}

.download-pdf-btn {
    background: #28a745;
    color: white;
    padding: 10px 20px;
    border: none;
    border-radius: 5px;
    cursor: pointer;
    text-decoration: none;
    display: inline-block;
    margin: 10px 0;
    transition: background 0.3s ease;
}

.download-pdf-btn:hover {
    background: #218838;
}

.download-pdf-btn.disabled {
    background: #6c757d;
    cursor: not-allowed;
    opacity: 0.6;
}
</style>
`;

// HTML template for PDF progress UI
const progressHTML = `
<div class="pdf-progress-container" id="pdf-loading" style="display: none;">
    <h5>Generating PDF...</h5>
    <div class="progress">
        <div class="progress-bar" id="pdf-progress" style="width: 0%;" role="progressbar"></div>
    </div>
    <div class="pdf-status" id="pdf-status">Initializing...</div>
    <div class="pdf-error" id="pdf-error"></div>
    <a href="#" class="download-pdf-btn disabled" id="download-pdf-btn" style="display: none;">
        📄 Download PDF
    </a>
</div>
`;

// Initialize and export
const pdfGenerator = new PDFGenerator();

// Add styles to page
document.head.insertAdjacentHTML('beforeend', progressStyles);

// Usage example:
// pdfGenerator.generatePDF(lectureId, authToken);
`;

console.log('PDF Generator with Progress Tracking loaded');
