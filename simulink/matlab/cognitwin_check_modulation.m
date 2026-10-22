function [ok, msg] = cognitwin_check_modulation(tx, modulation, meta)
%COGNITWIN_CHECK_MODULATION  Prove from the samples that tx is the configured scheme.
%
%   [ok, msg] = COGNITWIN_CHECK_MODULATION(tx, modulation, meta)
%
%   tx and meta come from cognitwin_waveform(). The test is structural, not
%   statistical, so it is exact:
%       BPSK       |tx| = 1 and imag(tx) = 0
%       QPSK       |tx| = 1 and angle(tx) in pi/4 + k*pi/2
%       OFDM-QPSK  every full symbol's cyclic prefix equals its last cpLen
%                  samples, and the envelope is not constant (PAPR > 3 dB)
%
%   Used by run_simulink_case (export gate) and diagnose_simulink_phy (D17).
    tx = tx(:);
    switch upper(strtrim(modulation))
        case 'BPSK'
            magErr = max(abs(abs(tx) - 1));
            imErr  = max(abs(imag(tx)));
            ok  = magErr < 1e-9 && imErr < 1e-9;
            msg = sprintf('BPSK: max||tx|-1| = %.1e, max|imag(tx)| = %.1e (both must be ~0)', ...
                          magErr, imErr);
        case 'QPSK'
            magErr = max(abs(abs(tx) - 1));
            ph     = angle(tx) - pi/4;
            phErr  = max(abs(ph - (pi/2)*round(ph/(pi/2))));
            ok  = magErr < 1e-9 && phErr < 1e-9;
            msg = sprintf('QPSK: max||tx|-1| = %.1e, max phase error vs pi/4 + k*pi/2 = %.1e', ...
                          magErr, phErr);
        case {'OFDM-QPSK', 'OFDM_QPSK', 'OFDM'}
            symLen = meta.nFFT + meta.cpLen;
            nFull  = floor(numel(tx) / symLen);
            cpErr  = 0;
            for s = 1:nFull
                blk   = tx((s-1)*symLen + (1:symLen));
                cpErr = max(cpErr, max(abs(blk(1:meta.cpLen) - blk(end-meta.cpLen+1:end))));
            end
            paprDb = 10*log10(max(abs(tx).^2) / mean(abs(tx).^2));
            ok  = nFull >= 1 && cpErr < 1e-12 && paprDb > 3;
            msg = sprintf(['OFDM: %d full symbols, max|CP - tail| = %.1e, PAPR %.1f dB ' ...
                           '(single-carrier PSK would be 0 dB)'], nFull, cpErr, paprDb);
        otherwise
            ok  = false;
            msg = sprintf('no modulation signature check for "%s"', modulation);
    end
end
