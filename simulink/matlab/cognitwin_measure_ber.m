function [ber, nErrors, nBits] = cognitwin_measure_ber(modulation, rxEq, bitsTx, meta)
%COGNITWIN_MEASURE_BER  Hard-decision demodulation and true bit-error counting.
%
%   [ber, nErrors, nBits] = COGNITWIN_MEASURE_BER(modulation, rxEq, bitsTx, meta)
%
%   rxEq must already be equalised (divided by the estimated channel gain). The
%   demapper is the exact inverse of cognitwin_waveform(): nearest-constellation
%   symbol decision, symbol index -> Gray codeword -> bits (MSB first).
%
%   Returns a MEASURED bit error rate. Nothing here is modelled or assumed.

    modulation = upper(strtrim(modulation));
    rxEq = rxEq(:);
    bitsTx = bitsTx(:);

    switch modulation
        case {'BPSK', 'QPSK'}
            M = meta.M; k = meta.k; sps = meta.sps;

            if sps > 1                      % matched-filter: average over each symbol
                nSym = floor(numel(rxEq) / sps);
                rxSym = mean(reshape(rxEq(1:nSym*sps), sps, nSym), 1).';
            else
                rxSym = rxEq;
                nSym  = numel(rxSym);
            end

            phaseOffset = 0;
            if M == 4, phaseOffset = pi/4; end
            constellation = exp(1i * (2*pi*(0:M-1).'/M + phaseOffset));

            nSym = min(nSym, floor(numel(bitsTx)/k));
            bitsRx = zeros(nSym*k, 1);
            for n = 1:nSym
                [~, idx] = min(abs(rxSym(n) - constellation));
                m = idx - 1;
                g = cognitwin_bin2gray(m);
                for b = 1:k
                    bitsRx((n-1)*k + b) = bitget(g, k - b + 1);
                end
            end

        case {'OFDM-QPSK', 'OFDM_QPSK', 'OFDM'}
            nFFT = meta.nFFT; cpLen = meta.cpLen; k = meta.k; M = meta.M;
            symLen = nFFT + cpLen;
            nOFDM = floor(numel(rxEq) / symLen);
            if nOFDM < 1
                ber = NaN; nErrors = 0; nBits = 0; return;
            end

            constellation = exp(1i * (2*pi*(0:M-1).'/M + pi/4));
            bitsRx = zeros(nOFDM * nFFT * k, 1);

            for s = 1:nOFDM
                blk = rxEq((s-1)*symLen + (1:symLen));
                blk = blk(cpLen+1:end);                 % strip cyclic prefix
                grid = fft(blk, nFFT) / sqrt(nFFT);     % matches ofdm.py normalisation
                for n = 1:nFFT
                    [~, idx] = min(abs(grid(n) - constellation));
                    m = idx - 1;
                    g = cognitwin_bin2gray(m);
                    base = ((s-1)*nFFT + (n-1)) * k;
                    for b = 1:k
                        bitsRx(base + b) = bitget(g, k - b + 1);
                    end
                end
            end

        otherwise
            error('cognitwin_measure_ber:UnknownModulation', ...
                  'Unsupported modulation "%s".', modulation);
    end

    nBits = min(numel(bitsRx), numel(bitsTx));
    if nBits == 0
        ber = NaN; nErrors = 0; return;
    end
    nErrors = sum(bitsRx(1:nBits) ~= bitsTx(1:nBits));
    ber = nErrors / nBits;
end
