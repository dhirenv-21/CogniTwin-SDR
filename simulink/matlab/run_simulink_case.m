function [outFile, m] = run_simulink_case(modulation, snrDb, interferencePower, channelType, opts)
%RUN_SIMULINK_CASE  Run ONE real Simulink PHY simulation, verify it, export it.
%
%   [outFile, m] = RUN_SIMULINK_CASE(modulation, snrDb, interferencePower, channelType, opts)
%
%   Arguments (all optional, shown with defaults):
%       modulation        'QPSK'      'BPSK' | 'QPSK' | 'OFDM-QPSK'
%       snrDb             20          channel SNR in dB
%       interferencePower 0           jammer power (tx power is normalised to 1,
%                                     so SIR_dB = -10*log10(interferencePower))
%       channelType       'AWGN'      'AWGN' | 'Rayleigh' | 'Rician'
%
%   opts (struct, optional):
%       .Fs             100e3   sample rate (Hz)
%       .nSamples       10000   number of I/Q samples
%       .seed           42      waveform + channel seed; the in-model noise seed
%                               is derived from it (NoiseSeed = seed + 1000)
%       .sps            1       samples per symbol (keep 1 to match the classifier)
%       .patternSymbols 0       0 = non-repeating stream; 32 = classifier training style
%       .name           auto    output file stem
%       .outDir         ../results
%       .timestamp      0
%       .verbose        true
%       .strict         true    abort instead of exporting a measurement that
%                               fails a physical-consistency check
%
%   EVERY reported quantity is computed from the actual logged arrays:
%
%       signal      = h .* tx           (h known exactly, supplied to the model)
%       noise       = noise_signal      (logged separately by the model)
%       jam         = interference_signal
%       P_sig       = mean(|h*tx|^2)
%       P_noise     = mean(|noise|^2)
%       P_jam       = mean(|jam|^2)
%       SNR_dB      = 10*log10(P_sig / P_noise)
%       SIR_dB      = 10*log10(P_sig / P_jam)
%       SINR_dB     = 10*log10(P_sig / (P_noise + P_jam))
%
%   Nothing is inferred from a least-squares fit, and nothing is exported unless
%   the run passes the consistency checks in local_verify().
%
%   SNR DEFINITION. snr_db is configured against the UNIT-POWER TRANSMIT
%   waveform, BEFORE fading and interference:  P_noise = 10^(-snr_db/10).
%   Two measured figures are exported so the reference is never ambiguous:
%       measured_snr_tx_ref_db = 10*log10(P_tx / P_noise)        pre-fading,
%                                directly comparable with snr_db
%       measured_snr_db        = 10*log10(|h|^2 P_tx / P_noise)  post-fading
%                                (received SNR), unchanged from v3
%   Interference never enters either SNR; it is reported as SIR / SINR.
%
%   EXAMPLES
%       run_simulink_case();
%       run_simulink_case('QPSK', 10, 0, 'AWGN');
%       run_simulink_case('OFDM-QPSK', 3, 2.5, 'Rayleigh');

    if nargin < 1 || isempty(modulation),        modulation = 'QPSK'; end
    if nargin < 2 || isempty(snrDb),             snrDb = 20;          end
    if nargin < 3 || isempty(interferencePower), interferencePower = 0; end
    if nargin < 4 || isempty(channelType),       channelType = 'AWGN'; end
    if nargin < 5,                               opts = struct();      end

    def = struct('Fs', 100e3, 'nSamples', 10000, 'seed', 42, 'sps', 1, ...
                 'patternSymbols', 0, 'name', '', 'outDir', '', ...
                 'timestamp', 0, 'verbose', true, 'strict', true);
    f = fieldnames(def);
    for i = 1:numel(f)
        if ~isfield(opts, f{i}) || isempty(opts.(f{i}))
            opts.(f{i}) = def.(f{i});
        end
    end

    thisDir     = fileparts(mfilename('fullpath'));
    simulinkDir = fileparts(thisDir);
    if isempty(opts.outDir)
        opts.outDir = fullfile(simulinkDir, 'results');
    end
    if ~exist(opts.outDir, 'dir'); mkdir(opts.outDir); end

    modelName = 'cognitwin_sdr_phy';
    modelPath = fullfile(simulinkDir, [modelName '.slx']);

    oldDir = pwd;
    cleanupDir = onCleanup(@() cd(oldDir));
    cd(simulinkDir);

    if ~exist(modelPath, 'file')
        error('run_simulink_case:MissingModel', ...
              ['Simulink model not found at %s.\n' ...
               'Create it with:  cd simulink; create_cognitwin_model'], modelPath);
    end

    if ~bdIsLoaded(modelName)
        load_system(modelName);
    end

    % ---------------------------------------------------- model version guard
    % v3 replaced the single complex INPUT_IQ block with two real INPUT_I /
    % INPUT_Q blocks. Running the v3 driver against a v1/v2 .slx would silently
    % reproduce the zero-signal bug, so refuse outright.
    blocks = find_system(modelName, 'SearchDepth', 1, 'BlockType', 'FromWorkspace');
    names  = cellfun(@(b) get_param(b,'Name'), blocks, 'UniformOutput', false);
    if ~all(ismember({'INPUT_I','INPUT_Q'}, names))
        error('run_simulink_case:OutdatedModel', ...
              ['The loaded model does not have the v3 INPUT_I / INPUT_Q real inputs\n' ...
               '(found: %s).\n' ...
               'This is the model version whose complex From Workspace input produced\n' ...
               'BER ~ 0.5 and |h| ~ 0.004. Rebuild it:\n' ...
               '    cd simulink; create_cognitwin_model'], strjoin(names, ', '));
    end

    % v4 seeds the noise, either through four Random Number blocks (default)
    % or through a NOISE_SEED constant feeding rng() inside PHY_Channel. A v3
    % .slx has neither, ignores every seed and gives every run the same noise
    % and jammer realisation, so refuse it.
    rnBlk   = find_system(modelName, 'SearchDepth', 1, 'BlockType', 'RandomNumber');
    rnNames = cellfun(@(b) get_param(b,'Name'), rnBlk, 'UniformOutput', false);
    seedBlk = find_system(modelName, 'SearchDepth', 1, 'Name', 'NOISE_SEED');
    if all(ismember({'NOISE_I','NOISE_Q','JAM_I','JAM_Q'}, rnNames))
        noiseSource = 'random_number_blocks';
    elseif ~isempty(seedBlk)
        noiseSource = 'block_rng';
    else
        error('run_simulink_case:UnseededModel', ...
              ['The loaded model has no seeded noise source (pre-v4 build).\n' ...
               'In that build randn inside PHY_Channel restarts from the same state\n' ...
               'every simulation, so every run reuses ONE noise realisation.\n' ...
               'Rebuild it:\n' ...
               '    cd simulink; create_cognitwin_model']);
    end

    % --------------------------------------------------------- channel model
    % Generated in the driver so it is exactly known, reproducible and exportable.
    % Distributions are the project specification's, unchanged.
    rng(opts.seed + 5000);
    switch upper(strtrim(channelType))
        case 'AWGN'
            h = 1 + 0i;                                    % no fading
        case 'RAYLEIGH'
            h = (randn + 1i*randn)/sqrt(2);                % CN(0,1), E|h|^2 = 1
        case 'RICIAN'
            K = 2;
            h = (sqrt(K) + (randn + 1i*randn)/sqrt(2))/sqrt(K+1);   % E|h|^2 = 1
        otherwise
            error('run_simulink_case:UnknownChannel', ...
                  'channelType must be AWGN, Rayleigh or Rician (got "%s").', channelType);
    end

    % ---------------------------------------------------------- the waveform
    N  = round(opts.nSamples);
    Fs = opts.Fs;
    [tx, bitsTx, meta] = cognitwin_waveform(modulation, N, opts.seed, opts.sps, opts.patternSymbols);
    tx = tx(:);

    pTx = mean(abs(tx).^2);
    if abs(pTx - 1) > 1e-9
        error('run_simulink_case:TxNotUnitPower', ...
              'Transmit waveform power is %.6f, expected 1. SIR/SNR bookkeeping assumes unit power.', pTx);
    end

    t = (0:N-1).' / Fs;

    % =====================================================================
    % INPUT FORMAT  (root cause of the v2 zero-signal failure)
    % ---------------------------------------------------------------------
    % v2 used   iq_input = [t, tx]   with tx COMPLEX, which made the entire
    % matrix complex - including column 1, the time vector. From Workspace's
    % array format needs a REAL monotonic time column, so the block resolved no
    % samples and emitted 0 for the whole run. The wanted signal never reached
    % PHY_Channel and every downstream number was measuring pure noise.
    %
    % v3 sends I and Q as two SEPARATE REAL matrices. No From Workspace block
    % ever receives complex data, so the time column cannot be corrupted.
    % =====================================================================
    iq_input_i = [t, real(tx)];
    iq_input_q = [t, imag(tx)];

    if ~isreal(iq_input_i) || ~isreal(iq_input_q)
        error('run_simulink_case:ComplexFromWorkspaceInput', ...
              'From Workspace inputs must be REAL. This is the v2 bug - do not reintroduce it.');
    end

    % Sample count: fixed-step solver runs t = 0..StopTime inclusive, i.e.
    % StopTime/Ts + 1 steps. StopTime = (N-1)/Fs gives exactly N steps.
    SimStopTime = (N - 1) / Fs;

    assignin('base', 'iq_input_i',        iq_input_i);
    assignin('base', 'iq_input_q',        iq_input_q);
    assignin('base', 'Fs',                Fs);
    assignin('base', 'SNR_dB',            snrDb);
    assignin('base', 'InterferencePower', interferencePower);
    assignin('base', 'ChannelGainRe',     real(h));
    assignin('base', 'ChannelGainIm',     imag(h));
    assignin('base', 'ChannelType',       channelType);
    assignin('base', 'ModulationType',    modulation);
    assignin('base', 'SimStopTime',       SimStopTime);

    % Noise / jammer realisation. rng() here would NOT reach the model: randn in
    % a MATLAB Function block uses the block's own generator. The seed is passed
    % in as NoiseSeed and applied inside PHY_Channel on its first step.
    noiseSeed = round(opts.seed) + 1000;
    if noiseSeed < 0 || noiseSeed >= 2^32
        error('run_simulink_case:BadSeed', ...
              'opts.seed + 1000 must lie in [0, 2^32) (got %g).', noiseSeed);
    end
    assignin('base', 'NoiseSeed',         noiseSeed);

    set_param(modelName, 'Solver', 'FixedStepDiscrete', ...
                         'FixedStep', '1/Fs', ...
                         'StopTime', 'SimStopTime');

    if opts.verbose
        fprintf('\n[Simulink] %s | SNR %.2f dB | interference %.4f | %s | N = %d | Fs = %.1f kHz | |h| = %.4f | noise seed %d\n', ...
                modulation, snrDb, interferencePower, channelType, N, Fs/1000, abs(h), noiseSeed);
    end

    tStart = tic;
    try
        simOut = sim(modelName, 'ReturnWorkspaceOutputs', 'on');
    catch errFirst
        try
            simOut = sim(modelName);
        catch errSecond
            error('run_simulink_case:SimulationFailed', ...
                  ['Simulink simulation failed - nothing exported.\n' ...
                   '  sim(...,''ReturnWorkspaceOutputs'',''on''): %s\n' ...
                   '  sim(model)                              : %s'], ...
                  errFirst.message, errSecond.message);
        end
    end
    simSeconds = toc(tStart);

    % ------------------------------------------------------- extract outputs
    [rx,   tOut] = local_unpack(local_get(simOut, 'rx_iq'),               'rx_iq');
    jam          = local_unpack(local_get(simOut, 'interference_signal'), 'interference_signal');
    noise        = local_unpack(local_get(simOut, 'noise_signal'),        'noise_signal');
    txEcho       = local_unpack(local_get(simOut, 'tx_echo'),             'tx_echo');

    rx = rx(:); tOut = tOut(:); jam = jam(:); noise = noise(:); txEcho = txEcho(:);

    % ---------------------------------------------- sample count (loud, never silent)
    if numel(rx) ~= N
        error('run_simulink_case:SampleCount', ...
              ['Logged %d samples for %d input samples. StopTime = %.9g, Ts = %.9g.\n' ...
               'Expected StopTime == (N-1)/Fs == %.9g.'], ...
              numel(rx), N, SimStopTime, 1/Fs, SimStopTime);
    end
    if any([numel(jam) numel(noise) numel(txEcho)] ~= N)
        error('run_simulink_case:SampleCountMismatch', ...
              'Logged lengths differ: rx=%d jam=%d noise=%d txEcho=%d (expected %d).', ...
              numel(rx), numel(jam), numel(noise), numel(txEcho), N);
    end

    % ==================================================================
    % CONSISTENCY CHECKS - a broken PHY must never be exported
    % ==================================================================
    chk = local_verify(tx, txEcho, rx, jam, noise, h, snrDb, interferencePower, t, tOut, Fs, ...
                       modulation, meta);

    if opts.verbose
        local_print_checks(chk);
    end

    if opts.strict && ~chk.ok
        error('run_simulink_case:PhysicsCheckFailed', ...
              ['PHY consistency check FAILED - measurement NOT exported.\n%s\n' ...
               'Nothing was written to disk. Run diagnose_simulink_phy for a node-by-node trace.'], ...
              strjoin(chk.failures, sprintf('\n')));
    end

    % ==================================================================
    % MEASUREMENTS - all from the actual arrays
    % ==================================================================
    sigArr = h * tx;                        % the wanted component as it enters the sum
    pSig   = mean(abs(sigArr).^2);
    pNoise = mean(abs(noise).^2);
    pJam   = mean(abs(jam).^2);
    pRx    = mean(abs(rx).^2);

    snrMeasDb  = 10*log10(pSig / max(pNoise, realmin));       % post-fading
    snrTxRefDb = 10*log10(pTx  / max(pNoise, realmin));       % pre-fading, vs snrDb
    if pJam > 0
        sirMeasDb = 10*log10(pSig / pJam);
    else
        sirMeasDb = Inf;
    end
    sinrMeasDb = 10*log10(pSig / max(pNoise + pJam, realmin));

    % Independent cross-check: least-squares channel estimate. With the signal
    % present this must land on the true h; on the v2 broken build it collapsed
    % to sqrt(P_rx/N), which is what chk.signalPresent detects.
    hLs   = (tx' * rx) / (tx' * tx);
    hErr  = abs(hLs - h) / max(abs(h), realmin);

    % ---------------------------------------------------------------- BER
    % Coherent single-tap equalisation with the KNOWN channel gain, then the
    % exact inverse of the transmit mapping.
    rxEq = rx / h;
    [ber, nErr, nBits] = cognitwin_measure_ber(modulation, rxEq, bitsTx, meta);

    % ---------------------------------------------------------------- export
    if isempty(opts.name)
        stem = sprintf('sim_%s_snr%s_int%s_%s', ...
                       lower(strrep(modulation, '-', '')), ...
                       local_num2tag(snrDb), local_num2tag(interferencePower), ...
                       lower(channelType));
    else
        stem = opts.name;
    end
    outFile = fullfile(opts.outDir, [stem '.mat']);

    m = struct();
    m.iq_samples                  = rx;
    m.tx_iq                       = tx;
    m.noise_iq                    = noise;
    m.interference_iq             = jam;
    m.time_vector                 = tOut;
    m.snr_db                      = double(snrDb);
    m.ber                         = double(ber);
    m.modulation                  = modulation;
    m.interference_power          = double(interferencePower);
    m.channel_type                = channelType;
    m.timestamp                   = double(opts.timestamp);
    m.sample_rate                 = double(Fs);
    m.num_samples                 = double(N);
    m.source                      = 'simulink';
    m.model_name                  = modelName;
    m.sim_stop_time               = double(SimStopTime);
    m.fixed_step                  = double(1/Fs);
    m.samples_per_symbol          = double(opts.sps);
    m.pattern_symbols             = double(opts.patternSymbols);
    m.seed                        = double(opts.seed);
    m.noise_seed                  = double(noiseSeed);
    m.model_version               = 'v4';
    m.noise_source                = noiseSource;
    m.run_id                      = sprintf('%s_seed%d_%s', stem, round(opts.seed), ...
                                            datestr(now, 'yyyymmddTHHMMSS'));
    m.snr_definition              = ['snr_db: P_noise = 10^(-snr_db/10) relative to unit-power tx, ' ...
                                     'before fading and interference. measured_snr_tx_ref_db = ' ...
                                     'P_tx/P_noise (pre-fading); measured_snr_db = |h|^2 P_tx/P_noise ' ...
                                     '(post-fading). Interference is excluded from SNR (see SIR/SINR).'];
    % --- powers measured from the arrays -------------------------------
    m.measured_signal_power       = double(pSig);
    m.measured_noise_power        = double(pNoise);
    m.measured_interference_power = double(pJam);
    m.measured_power              = double(pRx);
    m.measured_tx_power           = double(pTx);
    m.measured_snr_db             = double(snrMeasDb);
    m.measured_snr_tx_ref_db      = double(snrTxRefDb);
    m.measured_sir_db             = double(sirMeasDb);
    m.measured_sinr_db            = double(sinrMeasDb);
    % --- channel -------------------------------------------------------
    m.channel_gain_real           = double(real(h));
    m.channel_gain_imag           = double(imag(h));
    m.channel_gain_mag            = double(abs(h));
    m.channel_gain_ls_real        = double(real(hLs));
    m.channel_gain_ls_imag        = double(imag(hLs));
    m.channel_estimate_rel_error  = double(hErr);
    % --- BER -----------------------------------------------------------
    m.bit_errors                  = double(nErr);
    m.bits_compared               = double(nBits);
    % --- verification evidence -----------------------------------------
    m.check_tx_echo_max_error     = double(chk.txEchoMaxErr);
    m.check_sum_residual          = double(chk.sumResidual);
    m.check_jam_tx_correlation    = double(chk.jamTxCorr);
    m.check_signal_present        = double(chk.signalPresent);
    m.check_estimator_margin_db   = double(chk.estimatorMarginDb);
    m.check_noise_jam_correlation = double(chk.noiseJamCorr);
    m.check_noise_iq_balance_db   = double(chk.noiseIqBalanceDb);
    m.check_tx_matches_modulation = double(chk.txMatchesModulation);
    m.check_names                 = strjoin(chk.names, ',');
    m.checks_passed               = double(chk.ok);
    m.sim_wall_seconds            = double(simSeconds);

    save(outFile, '-struct', 'm', '-v7');

    if opts.verbose
        fprintf('[Simulink] P_sig %.6f | P_noise %.6f | P_jam %.6f | P_rx %.6f\n', ...
                pSig, pNoise, pJam, pRx);
        fprintf('[Simulink] SNR %.2f dB (tx-referenced %.2f dB vs configured %.2f) | SIR %.2f dB | SINR %.2f dB   (all from arrays)\n', ...
                snrMeasDb, snrTxRefDb, snrDb, sirMeasDb, sinrMeasDb);
        fprintf('[Simulink] |h| true %.4f | |h| LS %.4f | rel err %.2e\n', ...
                abs(h), abs(hLs), hErr);
        fprintf('[Simulink] BER %.6f (%d/%d bits) | %d samples | wall %.2f s\n', ...
                ber, nErr, nBits, N, simSeconds);
        fprintf('[Simulink] exported -> %s\n', outFile);
    end
end

% ======================================================================= checks

function chk = local_verify(tx, txEcho, rx, jam, noise, h, snrDb, interfPower, t, tOut, Fs, modulation, meta)
%LOCAL_VERIFY  Physical-consistency battery. Every check is computed from arrays.
%
%   Returns chk.ok, chk.failures (cell of strings), chk.lines (printable) plus
%   the individual measured quantities so they can be exported as evidence.

    N = numel(rx);
    names = {}; passed = []; msgs = {};

    % --- 1. the wanted signal actually reached PHY_Channel ------------------
    chk.txEchoMaxErr = max(abs(txEcho - tx));
    names{end+1} = 'tx_echo_matches_tx';
    passed(end+1) = chk.txEchoMaxErr < 1e-9;
    msgs{end+1} = sprintf(['max|tx_echo - tx| = %.3e  ' ...
        '(must be ~0; a large value means the From Workspace input is dead)'], chk.txEchoMaxErr);

    % --- 2. the model computed exactly y = h*x + jam + noise ---------------
    chk.sumResidual = max(abs(rx - (h*tx + jam + noise)));
    names{end+1} = 'rx_equals_hx_plus_n_j';
    passed(end+1) = chk.sumResidual < 1e-9;
    msgs{end+1} = sprintf('max|rx - (h*tx + jam + noise)| = %.3e', chk.sumResidual);

    % --- 3. noise power matches the requested SNR --------------------------
    pNoise   = mean(abs(noise).^2);
    pNoiseEx = 10^(-snrDb/10);
    noiseErrDb = abs(10*log10(max(pNoise,realmin)/pNoiseEx));
    chk.noiseErrDb = noiseErrDb;
    names{end+1} = 'noise_power_matches_snr';
    passed(end+1) = noiseErrDb < 0.5;
    msgs{end+1} = sprintf('measured %.6g vs expected 10^(-SNR/10) = %.6g  (%.2f dB error)', ...
                          pNoise, pNoiseEx, noiseErrDb);

    % --- 4. jammer power matches the request -------------------------------
    pJam = mean(abs(jam).^2);
    names{end+1} = 'jam_power_matches_request';
    if interfPower > 0
        jamErrDb = abs(10*log10(max(pJam,realmin)/interfPower));
        passed(end+1) = jamErrDb < 0.5;
        msgs{end+1} = sprintf('measured %.6g vs requested %.6g  (%.2f dB error)', ...
                              pJam, interfPower, jamErrDb);
    else
        passed(end+1) = (pJam == 0);
        msgs{end+1} = sprintf('measured %.6g with interference disabled', pJam);
    end

    % --- 5. the jammer is INDEPENDENT of the wanted signal -----------------
    % Guards against the v1 bug where "interference" was a coherent sqrt(P)*x.
    names{end+1} = 'jam_independent_of_tx';
    if interfPower > 0
        chk.jamTxCorr = abs(tx' * jam) / sqrt((tx'*tx) * max(jam'*jam, realmin));
        passed(end+1) = chk.jamTxCorr < 5/sqrt(N);
        msgs{end+1} = sprintf('|corr(tx, jam)| = %.5f  (threshold %.5f)', ...
                              chk.jamTxCorr, 5/sqrt(N));
    else
        chk.jamTxCorr = 0;
        passed(end+1) = true;
        msgs{end+1} = 'interference disabled';
    end

    % --- 6. the signal is genuinely present (the v2 smoking gun) -----------
    % A least-squares fit of tx to pure noise yields |h_LS|^2 ~ P_rx/N. With the
    % signal present, |h_LS|^2 sits far above that floor.
    hLs      = (tx' * rx) / (tx' * tx);
    pRx      = mean(abs(rx).^2);
    floorPow = pRx / N;
    chk.estimatorMarginDb = 10*log10(max(abs(hLs)^2, realmin) / max(floorPow, realmin));
    chk.signalPresent = chk.estimatorMarginDb > 10;
    names{end+1} = 'wanted_signal_present';
    passed(end+1) = chk.signalPresent;
    msgs{end+1} = sprintf(['|h_LS|^2 is %.1f dB above the pure-noise floor P_rx/N  ' ...
        '(need > 10 dB; the v2 build sat at ~0 dB)'], chk.estimatorMarginDb);

    % --- 7. LS estimate agrees with the true channel gain ------------------
    chk.hRelErr = abs(hLs - h)/max(abs(h),realmin);
    names{end+1} = 'ls_estimate_matches_h';
    passed(end+1) = chk.hRelErr < 0.25;
    msgs{end+1} = sprintf('|h| true %.4f, |h| LS %.4f, relative error %.4f', ...
                          abs(h), abs(hLs), chk.hRelErr);

    % --- 8. no NaN / Inf anywhere ------------------------------------------
    names{end+1} = 'all_samples_finite';
    passed(end+1) = all(isfinite(rx)) && all(isfinite(jam)) && all(isfinite(noise));
    msgs{end+1} = 'rx / jam / noise contain no NaN or Inf';

    % --- 9. time vector -----------------------------------------------------
    tErr = max(abs(tOut - t));
    names{end+1} = 'time_vector_correct';
    passed(end+1) = (tErr < 1e-12) && all(diff(tOut) > 0);
    msgs{end+1} = sprintf('max|t_logged - (0:N-1)/Fs| = %.3e, strictly increasing, Fs = %.1f Hz', ...
                          tErr, Fs);

    % --- 10. rx carries a genuine quadrature component ---------------------
    names{end+1} = 'rx_is_complex';
    passed(end+1) = any(imag(rx) ~= 0);
    msgs{end+1} = sprintf('non-zero imaginary samples: %d of %d', sum(imag(rx) ~= 0), N);

    % --- 11. the transmitted waveform really is the configured modulation --
    [chk.txMatchesModulation, modMsg] = cognitwin_check_modulation(tx, modulation, meta);
    names{end+1} = 'tx_matches_modulation';
    passed(end+1) = chk.txMatchesModulation;
    msgs{end+1} = modMsg;

    % --- 12. noise and jammer are independent of each other ---------------
    names{end+1} = 'noise_independent_of_jam';
    if interfPower > 0
        chk.noiseJamCorr = abs(noise' * jam) / sqrt(max(noise'*noise, realmin) * max(jam'*jam, realmin));
        passed(end+1) = chk.noiseJamCorr < 5/sqrt(N);
        msgs{end+1} = sprintf('|corr(noise, jam)| = %.5f  (threshold %.5f)', ...
                              chk.noiseJamCorr, 5/sqrt(N));
    else
        chk.noiseJamCorr = 0;
        passed(end+1) = true;
        msgs{end+1} = 'interference disabled';
    end

    % --- 13. the AWGN is circular: equal power in I and Q ------------------
    % Catches a real-only noise source or a mis-scaled quadrature branch,
    % either of which would bias every SNR and BER figure.
    vI = mean(real(noise).^2); vQ = mean(imag(noise).^2);
    chk.noiseIqBalanceDb = 10*log10(max(vI,realmin)/max(vQ,realmin));
    names{end+1} = 'noise_is_circular';
    passed(end+1) = abs(chk.noiseIqBalanceDb) < 0.5;
    msgs{end+1} = sprintf('P_noise,I / P_noise,Q = %.3f dB (must be within 0.5 dB)', chk.noiseIqBalanceDb);

    % --- roll up ------------------------------------------------------------
    chk.names = names;
    chk.ok = all(passed ~= 0);
    chk.failures = {};
    chk.lines = {};
    for i = 1:numel(names)
        chk.lines{end+1} = sprintf('  [%s] %-26s %s', local_tf(passed(i)), names{i}, msgs{i});
        if ~passed(i)
            chk.failures{end+1} = sprintf('  %s: %s', names{i}, msgs{i});
        end
    end
end

function s = local_tf(b)
    if b; s = 'PASS'; else; s = 'FAIL'; end
end

function local_print_checks(chk)
    fprintf('[Verify] PHY consistency checks:\n');
    for i = 1:numel(chk.lines)
        fprintf('%s\n', chk.lines{i});
    end
end

% ======================================================================= utils

function v = local_get(simOut, name)
    v = [];
    try
        if isa(simOut, 'Simulink.SimulationOutput')
            if any(strcmp(simOut.who, name))
                v = simOut.get(name);
            end
        elseif isstruct(simOut) && isfield(simOut, name)
            v = simOut.(name);
        end
    catch
        v = [];
    end
    if isempty(v)
        try
            v = evalin('base', name);
        catch
            v = [];
        end
    end
end

function [y, t] = local_unpack(s, label)
%LOCAL_UNPACK  Accept 'Structure With Time', 'Structure', 'Array' or timeseries.
    if isempty(s)
        error('run_simulink_case:MissingLog', ...
              ['Model produced no "%s" output.\n' ...
               'If the model predates v3, rebuild it: cd simulink; create_cognitwin_model'], label);
    end
    t = [];
    if isa(s, 'timeseries')
        y = squeeze(s.Data); t = s.Time;
    elseif isstruct(s) && isfield(s, 'signals')
        y = squeeze(s.signals.values);
        if isfield(s, 'time'); t = s.time; end
    else
        y = squeeze(s);
    end
    y = y(:);
    if isempty(t); t = (0:numel(y)-1).'; end
    t = t(:);
end

function tag = local_num2tag(x)
    tag = strrep(strrep(sprintf('%g', x), '.', 'p'), '-', 'm');
end
