function [tx, bits, meta] = cognitwin_waveform(modulation, nSamples, seed, sps, patternSymbols)
%COGNITWIN_WAVEFORM  Unit-power baseband transmit waveform for the CogniTwin PHY.
%
%   [tx, bits, meta] = COGNITWIN_WAVEFORM(modulation, nSamples, seed, sps, patternSymbols)
%
%   patternSymbols (default 0):
%     0  -> a genuinely non-repeating random symbol stream (what a real link carries)
%    >0  -> generate that many unique symbols and repeat them to fill the capture
%           (a repeating training / pilot pattern)
%
%   WHY THIS MATTERS. The existing Task-5 modulation classifier
%   (results/ai/modulation_classifier/rf_model.joblib) was trained exclusively on
%   blocks built from 32 unique symbols tiled 16x to 512 samples. That periodicity
%   dominates its spectral features, so on a non-repeating stream it reports
%   OFDM-QPSK for BPSK and QPSK alike. Setting patternSymbols = 32 reproduces the
%   training representation and restores correct detection. The proper fix is to
%   retrain the classifier on non-repeating data - see the Task 11 report.
%
%   Supported modulations:  'BPSK', 'QPSK', 'OFDM-QPSK'
%
%   The constellation mapping is a bit-exact match of the Python implementation in
%   src/modulation/digital/psk.py:
%
%       k        = log2(M)
%       g        = bits packed MSB-first             (Gray index)
%       m        = grayToBinary(g)                   (symbol index)
%       s(m)     = exp(1j*(2*pi*m/M + phaseOffset))  phaseOffset = pi/4 for M = 4
%
%   OFDM-QPSK matches src/multicarrier/ofdm.py: 64 subcarriers, 16-sample cyclic
%   prefix, ifft scaled by sqrt(n_fft).
%
%   IMPORTANT - sps (samples per symbol) defaults to 1. The CogniTwin modulation
%   classifier (results/ai/modulation_classifier/rf_model.joblib) was trained on
%   1 sample/symbol baseband. Oversampling (sps > 1) produces a physically valid
%   waveform but moves it away from the classifier's training representation, so
%   detection confidence will drop. Use sps = 1 unless you are deliberately testing
%   pulse-shaped waveforms.
%
%   Outputs:
%       tx    - nSamples x 1 complex column vector, mean power = 1
%       bits  - transmitted bit vector (column)
%       meta  - struct with fields: modulation, M, k, sps, nFFT, cpLen, nSymbols

    if nargin < 1 || isempty(modulation), modulation = 'QPSK';  end
    if nargin < 2 || isempty(nSamples),   nSamples   = 10000;   end
    if nargin < 3 || isempty(seed),       seed       = 42;      end
    if nargin < 4 || isempty(sps),        sps        = 1;       end
    if nargin < 5 || isempty(patternSymbols), patternSymbols = 0; end

    rng(seed);

    modulation = upper(strtrim(modulation));
    meta = struct('modulation', modulation, 'M', 0, 'k', 0, 'sps', sps, ...
                  'nFFT', 0, 'cpLen', 0, 'nSymbols', 0, ...
                  'patternSymbols', patternSymbols);

    switch modulation
        case {'BPSK', 'QPSK'}
            if strcmp(modulation, 'BPSK')
                M = 2; phaseOffset = 0;
            else
                M = 4; phaseOffset = pi/4;
            end
            k = log2(M);

            nSymbols = ceil(nSamples / sps);
            if patternSymbols > 0
                nUnique = min(patternSymbols, nSymbols);
            else
                nUnique = nSymbols;
            end

            uniqueBits = randi([0 1], nUnique * k, 1);

            symIdx = zeros(nUnique, 1);
            for n = 1:nUnique
                block = uniqueBits((n-1)*k + (1:k));
                g = 0;
                for b = 1:k
                    g = g * 2 + block(b);            % MSB-first packing
                end
                symIdx(n) = cognitwin_gray2bin(g);   % Gray -> binary symbol index
            end

            uniqueSyms = exp(1i * (2*pi*symIdx / M + phaseOffset));

            reps = ceil(nSymbols / nUnique);
            syms = repmat(uniqueSyms, reps, 1);
            syms = syms(1:nSymbols);
            bits = repmat(uniqueBits, reps, 1);
            bits = bits(1:nSymbols*k);

            if sps > 1
                tx = reshape(repmat(syms.', sps, 1), [], 1);
            else
                tx = syms;
            end
            tx = tx(1:nSamples);

            meta.M = M; meta.k = k; meta.nSymbols = nSymbols;

        case {'OFDM-QPSK', 'OFDM_QPSK', 'OFDM'}
            nFFT  = 64;
            cpLen = 16;
            symLen = nFFT + cpLen;              % 80 samples per OFDM symbol
            nOFDM  = ceil(nSamples / symLen);

            k = 2; M = 4; phaseOffset = pi/4;
            bits = randi([0 1], nOFDM * nFFT * k, 1);

            tx = zeros(nOFDM * symLen, 1);
            for s = 1:nOFDM
                symBits = bits((s-1)*nFFT*k + (1:nFFT*k));
                grid = zeros(nFFT, 1);
                for n = 1:nFFT
                    block = symBits((n-1)*k + (1:k));
                    g = block(1)*2 + block(2);
                    m = cognitwin_gray2bin(g);
                    grid(n) = exp(1i * (2*pi*m/M + phaseOffset));
                end
                timeSym = ifft(grid, nFFT) * sqrt(nFFT);
                cp      = timeSym(end-cpLen+1:end);
                tx((s-1)*symLen + (1:symLen)) = [cp; timeSym];
            end
            tx = tx(1:nSamples);

            meta.M = M; meta.k = k; meta.nFFT = nFFT;
            meta.cpLen = cpLen; meta.nSymbols = nOFDM;

        otherwise
            error('cognitwin_waveform:UnknownModulation', ...
                  'Unsupported modulation "%s". Use BPSK, QPSK or OFDM-QPSK.', modulation);
    end

    % Normalise to exactly unit mean power so that
    %   SIR_dB = -10*log10(InterferencePower)
    % holds exactly for the interference model in the Simulink PHY_Channel block.
    p = mean(abs(tx).^2);
    if p > 0
        tx = tx / sqrt(p);
    end
    tx = tx(:);
end
