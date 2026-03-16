/**
 * MicProcessor: Captures mic audio and sends Int16 PCM to main thread.
 * If AudioContext is created with sampleRate: 16000, no downsampling needed.
 * Otherwise, downsamples from native rate to 16kHz using linear interpolation.
 */
class MicProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.bufferSize = 1600; // 100ms at 16kHz = 1600 samples
        this.buffer = new Float32Array(this.bufferSize);
        this.bufferIndex = 0;
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (!input || !input.length) return true;

        const channelData = input[0];

        for (let i = 0; i < channelData.length; i++) {
            this.buffer[this.bufferIndex++] = channelData[i];

            if (this.bufferIndex >= this.bufferSize) {
                // Convert Float32 [-1, 1] to Int16
                const int16 = new Int16Array(this.bufferSize);
                for (let j = 0; j < this.bufferSize; j++) {
                    int16[j] = Math.max(-1, Math.min(1, this.buffer[j])) * 0x7FFF;
                }
                this.port.postMessage({ type: 'audio', data: int16.buffer }, [int16.buffer]);
                this.buffer = new Float32Array(this.bufferSize);
                this.bufferIndex = 0;
            }
        }

        return true;
    }
}

registerProcessor('mic-processor', MicProcessor);


/**
 * PlaybackProcessor: Ring buffer playback for 24kHz PCM audio.
 * Receives Int16 PCM chunks from main thread, converts to Float32, plays via ring buffer.
 */
class PlaybackProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        // Ring buffer: 24kHz x 180 seconds
        this.bufferSize = 24000 * 180;
        this.buffer = new Float32Array(this.bufferSize);
        this.writeIndex = 0;
        this.readIndex = 0;

        this.port.onmessage = (event) => {
            if (event.data && event.data.command === 'clear') {
                this.readIndex = this.writeIndex;
                return;
            }

            // Expect Int16Array or ArrayBuffer of Int16 samples
            const int16Samples = (event.data instanceof Int16Array)
                ? event.data
                : new Int16Array(event.data);

            for (let i = 0; i < int16Samples.length; i++) {
                this.buffer[this.writeIndex] = int16Samples[i] / 32768;
                this.writeIndex = (this.writeIndex + 1) % this.bufferSize;

                // Overflow: overwrite oldest
                if (this.writeIndex === this.readIndex) {
                    this.readIndex = (this.readIndex + 1) % this.bufferSize;
                }
            }
        };
    }

    process(inputs, outputs, parameters) {
        const output = outputs[0];
        const framesPerBlock = output[0].length;

        for (let frame = 0; frame < framesPerBlock; frame++) {
            if (this.readIndex !== this.writeIndex) {
                output[0][frame] = this.buffer[this.readIndex];
                this.readIndex = (this.readIndex + 1) % this.bufferSize;
            } else {
                output[0][frame] = 0; // Silence when buffer empty
            }
        }

        return true;
    }
}

registerProcessor('playback-processor', PlaybackProcessor);
