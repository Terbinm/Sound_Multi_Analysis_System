/**
 * AudioFFTPlayer - Audio player with FFT visualization
 * Uses Web Audio API for real-time frequency analysis
 */
class AudioFFTPlayer {
    constructor(options = {}) {
        this.audioElement = null;
        this.audioContext = null;
        this.analyser = null;
        this.source = null;
        this.canvas = null;
        this.canvasContext = null;
        this.animationId = null;
        this.isInitialized = false;

        // Configuration
        this.fftSize = options.fftSize || 256;  // 128 frequency bins
        this.smoothingTimeConstant = options.smoothingTimeConstant || 0.8;
        this.barColor = options.barColor || '#3b82f6';  // Blue
        this.barColorPeak = options.barColorPeak || '#ef4444';  // Red for peaks
        this.backgroundColor = options.backgroundColor || '#1f2937';  // Dark gray

        // Callbacks
        this.onPlay = options.onPlay || null;
        this.onPause = options.onPause || null;
        this.onEnded = options.onEnded || null;
        this.onTimeUpdate = options.onTimeUpdate || null;
        this.onLoadedMetadata = options.onLoadedMetadata || null;
        this.onError = options.onError || null;
    }

    /**
     * Initialize the player with audio and canvas elements
     * @param {string} audioUrl - URL of the audio file
     * @param {HTMLCanvasElement} canvas - Canvas element for FFT visualization
     */
    init(audioUrl, canvas) {
        if (this.isInitialized) {
            this.destroy();
        }

        // Create audio element
        this.audioElement = new Audio();
        this.audioElement.crossOrigin = 'anonymous';
        this.audioElement.preload = 'metadata';

        // Set up event listeners
        this.audioElement.addEventListener('play', () => {
            this.startVisualization();
            if (this.onPlay) this.onPlay();
        });

        this.audioElement.addEventListener('pause', () => {
            this.stopVisualization();
            if (this.onPause) this.onPause();
        });

        this.audioElement.addEventListener('ended', () => {
            this.stopVisualization();
            if (this.onEnded) this.onEnded();
        });

        this.audioElement.addEventListener('timeupdate', () => {
            if (this.onTimeUpdate) {
                this.onTimeUpdate({
                    currentTime: this.audioElement.currentTime,
                    duration: this.audioElement.duration
                });
            }
        });

        this.audioElement.addEventListener('loadedmetadata', () => {
            if (this.onLoadedMetadata) {
                this.onLoadedMetadata({
                    duration: this.audioElement.duration
                });
            }
        });

        this.audioElement.addEventListener('error', (e) => {
            if (this.onError) {
                this.onError(e);
            }
        });

        // Set canvas
        this.canvas = canvas;
        this.canvasContext = canvas.getContext('2d');

        // Set audio source
        this.audioElement.src = audioUrl;

        this.isInitialized = true;
    }

    /**
     * Initialize Web Audio API context (must be called after user interaction)
     */
    initAudioContext() {
        if (this.audioContext) return;

        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = this.fftSize;
            this.analyser.smoothingTimeConstant = this.smoothingTimeConstant;

            // Connect audio element to analyser
            this.source = this.audioContext.createMediaElementSource(this.audioElement);
            this.source.connect(this.analyser);
            this.analyser.connect(this.audioContext.destination);
        } catch (e) {
            console.error('Failed to initialize Web Audio API:', e);
        }
    }

    /**
     * Play the audio
     */
    async play() {
        if (!this.audioElement) return;

        // Initialize audio context on first play (requires user interaction)
        this.initAudioContext();

        // Resume audio context if suspended
        if (this.audioContext && this.audioContext.state === 'suspended') {
            await this.audioContext.resume();
        }

        try {
            await this.audioElement.play();
        } catch (e) {
            console.error('Failed to play audio:', e);
            if (this.onError) this.onError(e);
        }
    }

    /**
     * Pause the audio
     */
    pause() {
        if (this.audioElement) {
            this.audioElement.pause();
        }
    }

    /**
     * Toggle play/pause
     */
    togglePlay() {
        if (this.audioElement) {
            if (this.audioElement.paused) {
                this.play();
            } else {
                this.pause();
            }
        }
    }

    /**
     * Seek to a specific time
     * @param {number} time - Time in seconds
     */
    seek(time) {
        if (this.audioElement) {
            this.audioElement.currentTime = Math.max(0, Math.min(time, this.audioElement.duration || 0));
        }
    }

    /**
     * Seek to a percentage of the duration
     * @param {number} percent - Percentage (0-100)
     */
    seekPercent(percent) {
        if (this.audioElement && this.audioElement.duration) {
            const time = (percent / 100) * this.audioElement.duration;
            this.seek(time);
        }
    }

    /**
     * Set volume
     * @param {number} volume - Volume level (0-1)
     */
    setVolume(volume) {
        if (this.audioElement) {
            this.audioElement.volume = Math.max(0, Math.min(1, volume));
        }
    }

    /**
     * Get current volume
     * @returns {number} Current volume (0-1)
     */
    getVolume() {
        return this.audioElement ? this.audioElement.volume : 1;
    }

    /**
     * Get current playback state
     * @returns {boolean} True if playing
     */
    isPlaying() {
        return this.audioElement && !this.audioElement.paused;
    }

    /**
     * Get current time
     * @returns {number} Current time in seconds
     */
    getCurrentTime() {
        return this.audioElement ? this.audioElement.currentTime : 0;
    }

    /**
     * Get duration
     * @returns {number} Duration in seconds
     */
    getDuration() {
        return this.audioElement ? this.audioElement.duration : 0;
    }

    /**
     * Start FFT visualization
     */
    startVisualization() {
        if (!this.analyser || !this.canvas) return;

        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const draw = () => {
            this.animationId = requestAnimationFrame(draw);

            this.analyser.getByteFrequencyData(dataArray);

            const width = this.canvas.width;
            const height = this.canvas.height;

            // Clear canvas
            this.canvasContext.fillStyle = this.backgroundColor;
            this.canvasContext.fillRect(0, 0, width, height);

            // Draw frequency bars
            const barWidth = (width / bufferLength) * 2.5;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                const barHeight = (dataArray[i] / 255) * height;

                // Gradient color based on intensity
                const intensity = dataArray[i] / 255;
                if (intensity > 0.8) {
                    this.canvasContext.fillStyle = this.barColorPeak;
                } else {
                    this.canvasContext.fillStyle = this.barColor;
                }

                // Draw bar from bottom
                this.canvasContext.fillRect(x, height - barHeight, barWidth - 1, barHeight);

                x += barWidth;
            }
        };

        draw();
    }

    /**
     * Stop FFT visualization
     */
    stopVisualization() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
            this.animationId = null;
        }

        // Draw final frame (static view)
        if (this.canvas && this.canvasContext) {
            const width = this.canvas.width;
            const height = this.canvas.height;
            this.canvasContext.fillStyle = this.backgroundColor;
            this.canvasContext.fillRect(0, 0, width, height);

            // Draw a subtle baseline
            this.canvasContext.strokeStyle = this.barColor + '40';
            this.canvasContext.beginPath();
            this.canvasContext.moveTo(0, height - 2);
            this.canvasContext.lineTo(width, height - 2);
            this.canvasContext.stroke();
        }
    }

    /**
     * Format time as MM:SS
     * @param {number} seconds - Time in seconds
     * @returns {string} Formatted time string
     */
    static formatTime(seconds) {
        if (isNaN(seconds) || !isFinite(seconds)) return '00:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }

    /**
     * Destroy the player and clean up resources
     */
    destroy() {
        this.stopVisualization();

        if (this.audioElement) {
            this.audioElement.pause();
            this.audioElement.src = '';
            this.audioElement = null;
        }

        if (this.source) {
            this.source.disconnect();
            this.source = null;
        }

        if (this.analyser) {
            this.analyser.disconnect();
            this.analyser = null;
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        this.canvas = null;
        this.canvasContext = null;
        this.isInitialized = false;
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AudioFFTPlayer;
}
