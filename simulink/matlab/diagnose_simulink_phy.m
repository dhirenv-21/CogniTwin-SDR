function report = diagnose_simulink_phy(verbose)
%DIAGNOSE_SIMULINK_PHY  Node-by-node health check of the CogniTwin-SDR Simulink PHY.
%
%   report = DIAGNOSE_SIMULINK_PHY()
%
%   Run this BEFORE trusting any run_simulink_case result. It walks the signal
%   path one node at a time and prints what it actually measured at each point,
%   so a fault is localised instead of guessed at:
%
%       D1  model exists, loads, compiles
%       D2  model is the v3 build (real INPUT_I / INPUT_Q inputs)
%       D3  From Workspace really passes a REAL test signal through unchanged
%       D4  From Workspace input-format contract: the real [t,I]/[t,Q] inputs are
%           accepted, complex time columns and the legacy [t,complex tx] are rejected
%       D5  PHY_Channel reconstructs x = complex(xi, xq) exactly (tx_echo)
%       D6  noise power == 10^(-SNR/10) across a range of SNRs
%       D7  jammer power == InterferencePower, and is independent of the signal
%       D8  channel gain h is applied exactly as supplied
%       D9  rx == h*tx + jam + noise, sample for sample
%       D10 sample count, time vector, sample rate
%       D11 noiseless loopback: SNR = +200 dB, no jammer -> rx must equal tx
%       D12 end-to-end BER sanity at high SNR
%       D13 noise seed control: same NoiseSeed -> identical noise and jammer,
%           different NoiseSeed -> uncorrelated realisations (the v3 defect)
%       D14 noise is circular and independent of the jammer
%       D15 interference has its expected measurable effect (P_rx, BER)
%       D16 fading has its expected measurable effect (P_rx scales by |h|^2, BER)
%       D17 each configured modulation is actually transmitted and demodulates
%       D18 run_simulink_case export contains every field the Python bridge reads
%
%   D1-D17 export nothing. D18 writes one MAT file to tempdir and deletes it.

    if nargin < 1 || isempty(verbose); verbose = true; end

    thisDir     = fileparts(mfilename('fullpath'));
    simulinkDir = fileparts(thisDir);
    modelName   = 'cognitwin_sdr_phy';
    modelPath   = fullfile(simulinkDir, [modelName '.slx']);

    oldDir = pwd;
    cleanupDir = onCleanup(@() cd(oldDir));
    cd(simulinkDir);

    report = struct('name', {}, 'ok', {}, 'detail', {});

    fprintf('\n================================================================\n');
    fprintf(' COGNITWIN-SDR SIMULINK PHY DIAGNOSTIC\n');
    fprintf('================================================================\n');
    fprintf(' MATLAB  : %s\n', version);
    fprintf(' Model   : %s\n', modelPath);
    fprintf('----------------------------------------------------------------\n');

    Fs = 100e3;
    N  = 2048;
    t  = (0:N-1).'/Fs;

    % ---------------------------------------------------------------- D1
    ok = exist(modelPath, 'file') == 4 || exist(modelPath, 'file') == 2;
    report = local_add(report, 'D1_model_exists', ok, modelPath);
    if ~ok
        local_print(report, verbose);
        error('diagnose_simulink_phy:MissingModel', ...
              'Model not found. Run:  cd simulink; create_cognitwin_model');
    end

    if ~bdIsLoaded(modelName); load_system(modelName); end
    report = local_add(report, 'D2_model_loads', true, 'load_system succeeded');

    % ---------------------------------------------------------------- D2
    fwBlocks = find_system(modelName, 'SearchDepth', 1, 'BlockType', 'FromWorkspace');
    fwNames  = cellfun(@(b) get_param(b,'Name'), fwBlocks, 'UniformOutput', false);
    isV3 = all(ismember({'INPUT_I','INPUT_Q'}, fwNames));
    report = local_add(report, 'D3_is_v3_build', isV3, ...
        sprintf('From Workspace blocks: %s', strjoin(fwNames, ', ')));
    if ~isV3
        local_print(report, verbose);
        error('diagnose_simulink_phy:OutdatedModel', ...
              ['This is not the v3 model. The v1/v2 builds fed a COMPLEX matrix to a\n' ...
               'single INPUT_IQ From Workspace block, which zeroed the wanted signal.\n' ...
               'Rebuild:  cd simulink; create_cognitwin_model']);
    end

    seedBlk = find_system(modelName, 'SearchDepth', 1, 'Name', 'NOISE_SEED');
    rnBlk   = find_system(modelName, 'SearchDepth', 1, 'BlockType', 'RandomNumber');
    rnNames = cellfun(@(b) get_param(b,'Name'), rnBlk, 'UniformOutput', false);
    hasRn   = all(ismember({'NOISE_I','NOISE_Q','JAM_I','JAM_Q'}, rnNames));
    if hasRn
        seedTxt = ['Random Number blocks NOISE_I/Q, JAM_I/Q, seeds: ' ...
                   strjoin(cellfun(@(b) get_param(b,'Seed'), rnBlk, 'UniformOutput', false), ' | ')];
    elseif ~isempty(seedBlk)
        seedTxt = 'NOISE_SEED constant -> rng() inside PHY_Channel';
    else
        seedTxt = 'NO seeded noise source (v3 build): every run reuses one noise realisation';
    end
    report = local_add(report, 'D3b_has_noise_seed_input', hasRn || ~isempty(seedBlk), seedTxt);

    % ---------------------------------------------------------------- D4
    % FROM WORKSPACE INPUT-FORMAT CONTRACT
    %
    % Previously this check asked  ~isreal(legacyInput(:,1))  - the complexity of
    % the EXTRACTED time column. That is the wrong object. Complexity is a
    % property of the whole array: [t, complex_tx] is complex (isreal == 0), which
    % is exactly what From Workspace rejects, but extracting column 1 yields an
    % all-zero imaginary part which MATLAB narrows straight back to real
    % (isreal == 1). The check therefore reported FAIL on a healthy v3 build.
    %
    % D4 now validates the INTENDED architecture and keeps a negative control:
    %
    %   D4a  iq_input_i (the real matrix the model actually consumes) ACCEPTED
    %   D4b  iq_input_q                                               ACCEPTED
    %   D4c  I + 1i*Q reconstructs the transmit waveform exactly
    %   D4d  legacy [t, complex_tx]                                   REJECTED
    %   D4e  iq_input_i with a complexified time column               REJECTED
    %
    % D4e is the live regression guard: if anything ever makes the INPUT_I or
    % INPUT_Q time column complex again, the contract check catches it.
    txProbe = exp(1i*(2*pi*randi([0 3], N, 1)/4 + pi/4));

    inputI = [t, real(txProbe)];      % exactly what local_sim / run_simulink_case build
    inputQ = [t, imag(txProbe)];

    [okI, whyI] = local_check_fw_input(inputI);
    [okQ, whyQ] = local_check_fw_input(inputQ);

    reconErr  = max(abs((inputI(:,2) + 1i*inputQ(:,2)) - txProbe));
    okRecon   = reconErr < 1e-15;

    % Negative control: the v2 format must be rejected by the same validator.
    [okLegacyAccepted, whyLegacy] = local_check_fw_input([t, txProbe]);
    okLegacyRejected = ~okLegacyAccepted;

    % Regression guard: the defect that matters is "the matrix handed to From
    % Workspace is complex". There are two distinct ways the time column can
    % cause that, and both must be rejected:
    %
    %   badRealImag  the time column carries a genuinely non-zero imaginary part
    %   badForced    complex storage is forced on the whole matrix (complex(M,0))
    %
    % Note deliberately NOT included: [complex(t, zeros(size(t))), real(tx)].
    % Concatenating a zero-imaginary array with a real one narrows the result
    % straight back to a real matrix, so that construction is not a defect at all
    % - From Workspace receives a real matrix and behaves correctly. Treating it
    % as a failure would be testing MATLAB's storage bookkeeping rather than the
    % property the block actually depends on.
    badRealImag = [t + 1i*eps, real(txProbe)];
    badForced   = complex([t, real(txProbe)], zeros(numel(t), 2));
    [okBad1, ~] = local_check_fw_input(badRealImag);
    [okBad2, ~] = local_check_fw_input(badForced);
    okComplexTimeRejected = ~okBad1 && ~okBad2;

    d4ok = okI && okQ && okRecon && okLegacyRejected && okComplexTimeRejected;

    report = local_add(report, 'D4_input_format_contract', d4ok, ...
        sprintf(['D4a iq_input_i %s | D4b iq_input_q %s | D4c I+jQ==tx (err %.1e) %s | ' ...
                 'D4d legacy [t,complex tx] rejected %s (%s) | ' ...
                 'D4e complex time column rejected %s'], ...
                local_tf(okI), local_tf(okQ), reconErr, local_tf(okRecon), ...
                local_tf(okLegacyRejected), whyLegacy, local_tf(okComplexTimeRejected)));

    if ~okI; fprintf(2, '      D4a detail: %s\n', whyI); end
    if ~okQ; fprintf(2, '      D4b detail: %s\n', whyQ); end

    % ---------------------------------------------------------------- D5-D10
    fprintf('\n-- running instrumented simulations --\n');

    snrList = [0 10 20 40];
    noiseOk = true; noiseDetail = '';
    for s = snrList
        r = local_sim(modelName, t, txProbe, s, 0, 1+0i, Fs, N);
        pN  = mean(abs(r.noise).^2);
        pEx = 10^(-s/10);
        errDb = abs(10*log10(max(pN,realmin)/pEx));
        noiseOk = noiseOk && (errDb < 0.6);
        noiseDetail = [noiseDetail sprintf('SNR %4.0f dB: P_n = %.6g (expected %.6g, %.2f dB err)  ', ...
                                            s, pN, pEx, errDb)]; %#ok<AGROW>
    end
    report = local_add(report, 'D6_noise_power_vs_snr', noiseOk, strtrim(noiseDetail));

    % single reference run for the structural checks
    r = local_sim(modelName, t, txProbe, 10, 0.25, 0.6+0.3i, Fs, N);

    echoErr = max(abs(r.txEcho - txProbe));
    report = local_add(report, 'D5_phy_reconstructs_x', echoErr < 1e-12, ...
        sprintf('max|tx_echo - tx| = %.3e', echoErr));

    pJam = mean(abs(r.jam).^2);
    jamErrDb = abs(10*log10(max(pJam,realmin)/0.25));
    corrJam = abs(txProbe' * r.jam) / sqrt((txProbe'*txProbe)*max(r.jam'*r.jam, realmin));
    report = local_add(report, 'D7_jam_power_and_independence', ...
        jamErrDb < 0.6 && corrJam < 5/sqrt(N), ...
        sprintf('P_jam = %.6g (requested 0.25, %.2f dB err); |corr(tx,jam)| = %.5f (threshold %.5f)', ...
                pJam, jamErrDb, corrJam, 5/sqrt(N)));

    hTrue = 0.6+0.3i;
    hLs   = (txProbe' * r.rx) / (txProbe' * txProbe);
    report = local_add(report, 'D8_channel_gain_applied', abs(hLs - hTrue) < 0.05, ...
        sprintf('supplied h = %.4f%+.4fi, LS estimate = %.4f%+.4fi', ...
                real(hTrue), imag(hTrue), real(hLs), imag(hLs)));

    resid = max(abs(r.rx - (hTrue*txProbe + r.jam + r.noise)));
    report = local_add(report, 'D9_rx_equals_model_equation', resid < 1e-12, ...
        sprintf('max|rx - (h*tx + jam + noise)| = %.3e', resid));

    tErr = max(abs(r.t - t));
    report = local_add(report, 'D10_sample_count_and_time', ...
        numel(r.rx) == N && tErr < 1e-12 && all(diff(r.t) > 0), ...
        sprintf('N logged = %d (expected %d), max time error = %.3e, StopTime = (N-1)/Fs = %.9g', ...
                numel(r.rx), N, tErr, (N-1)/Fs));

    % ---------------------------------------------------------------- D11
    % Noiseless loopback. With SNR = +200 dB, no jammer and h = 1, the received
    % waveform must be the transmitted waveform to numerical precision. This is
    % the single most decisive test of the input path.
    rl = local_sim(modelName, t, txProbe, 200, 0, 1+0i, Fs, N);
    loopErr = max(abs(rl.rx - txProbe));
    report = local_add(report, 'D11_noiseless_loopback', loopErr < 1e-6, ...
        sprintf('max|rx - tx| with SNR=200 dB, no jammer, h=1 : %.3e  (v2 build gave ~1.0)', loopErr));

    % ---------------------------------------------------------------- D12
    % End-to-end BER at high SNR must be 0, and near 0.5 only when there is
    % genuinely no usable signal.
    [txQ, bitsQ, metaQ] = cognitwin_waveform('QPSK', N, 7, 1, 0);
    rq = local_sim(modelName, t, txQ, 30, 0, 1+0i, Fs, N);
    berHigh = cognitwin_measure_ber('QPSK', rq.rx, bitsQ, metaQ);
    rq2 = local_sim(modelName, t, txQ, 0, 0, 1+0i, Fs, N);
    berLow = cognitwin_measure_ber('QPSK', rq2.rx, bitsQ, metaQ);
    report = local_add(report, 'D12_ber_sanity', berHigh < 1e-3 && berLow > berHigh, ...
        sprintf('QPSK BER: %.6f at 30 dB, %.6f at 0 dB (theory ~0.0 and ~0.159)', berHigh, berLow));

    % ---------------------------------------------------------------- D13
    % Seed control. Measured on the v3 exports: noise_iq was bit-identical for
    % seeds 11, 23 and 37 because randn in the MATLAB Function block ignores the
    % global rng. Same seed must reproduce; a different seed must decorrelate.
    thr  = 5/sqrt(N);
    sA1  = local_sim(modelName, t, txProbe, 10, 0.25, 1+0i, Fs, N, 1101);
    sA2  = local_sim(modelName, t, txProbe, 10, 0.25, 1+0i, Fs, N, 1101);
    sB   = local_sim(modelName, t, txProbe, 10, 0.25, 1+0i, Fs, N, 2202);
    repErr  = max([abs(sA1.noise - sA2.noise); abs(sA1.jam - sA2.jam)]);
    cNoise  = local_corr(sA1.noise, sB.noise);
    cJam    = local_corr(sA1.jam,   sB.jam);
    report = local_add(report, 'D13_noise_seed_control', ...
        repErr < 1e-12 && cNoise < thr && cJam < thr, ...
        sprintf(['same seed: max|diff| = %.1e (must be 0) | different seed: |corr(noise)| = %.4f, ' ...
                 '|corr(jam)| = %.4f (threshold %.4f; 1.0 means the seed is ignored)'], ...
                repErr, cNoise, cJam, thr));

    % ---------------------------------------------------------------- D14
    cNJ   = local_corr(sA1.noise, sA1.jam);
    balDb = 10*log10(mean(real(sA1.noise).^2) / mean(imag(sA1.noise).^2));
    report = local_add(report, 'D14_noise_circular_and_independent', ...
        cNJ < thr && abs(balDb) < 0.5, ...
        sprintf('|corr(noise, jam)| = %.4f (threshold %.4f) | P_I/P_Q of noise = %.2f dB (within 0.5)', ...
                cNJ, thr, balDb));

    % ---------------------------------------------------------------- D15
    % Interference effect, same noise seed so only the jammer differs.
    r0 = local_sim(modelName, t, txQ, 10, 0, 1+0i, Fs, N, 3303);
    r1 = local_sim(modelName, t, txQ, 10, 1, 1+0i, Fs, N, 3303);
    dPrx  = mean(abs(r1.rx).^2) - mean(abs(r0.rx).^2);
    ber0  = cognitwin_measure_ber('QPSK', r0.rx, bitsQ, metaQ);
    ber1  = cognitwin_measure_ber('QPSK', r1.rx, bitsQ, metaQ);
    report = local_add(report, 'D15_interference_effect', ...
        abs(dPrx - 1) < 0.15 && ber1 > ber0 && ber1 > 0.05, ...
        sprintf(['P = 0 -> 1: P_rx rises by %.3f (expected ~1.0) | QPSK BER %.5f -> %.5f ' ...
                 '(theory ~7.8e-4 -> ~0.15)'], dPrx, ber0, ber1));

    % ---------------------------------------------------------------- D16
    % Fading effect: a known weak gain must scale received signal power by
    % |h|^2 and raise BER (equalised by the known h, as run_simulink_case does).
    hf = 0.3*exp(1i*0.7);
    rf = local_sim(modelName, t, txQ, 10, 0, hf, Fs, N, 3303);
    pSigF  = mean(abs(rf.rx - rf.noise - rf.jam).^2);
    berF   = cognitwin_measure_ber('QPSK', rf.rx / hf, bitsQ, metaQ);
    report = local_add(report, 'D16_fading_effect', ...
        abs(pSigF - abs(hf)^2) < 1e-9 && berF > ber0 && berF > 0.05, ...
        sprintf(['h = %.2f*exp(j0.7): received signal power %.5f (expected |h|^2 = %.5f) | ' ...
                 'QPSK BER %.5f vs %.5f unfaded (theory at 10log10(0.09*10) = -0.46 dB: ~0.17)'], ...
                abs(hf), pSigF, abs(hf)^2, berF, ber0));

    % ---------------------------------------------------------------- D17
    % Modulation identity: the configured scheme is what is transmitted, it
    % survives the model, and it demodulates error-free at high SNR.
    mods = {'BPSK', 'QPSK', 'OFDM-QPSK'};
    nMod = 80*ceil(N/80);                       % whole OFDM symbols
    tMod = (0:nMod-1).'/Fs;
    modOk = true; modDetail = '';
    for k = 1:numel(mods)
        [txM, bitsM, metaM] = cognitwin_waveform(mods{k}, nMod, 50 + k, 1, 0);
        [sigOk, sigMsg] = cognitwin_check_modulation(txM, mods{k}, metaM);
        rm = local_sim(modelName, tMod, txM, 30, 0, 1+0i, Fs, nMod, 4404);
        [berM, ~, nbM] = cognitwin_measure_ber(mods{k}, rm.rx, bitsM, metaM);
        okK = sigOk && berM < 1e-3 && nbM > 0;
        modOk = modOk && okK;
        modDetail = [modDetail sprintf('%s [%s] BER@30dB %.1e over %d bits; ', ...
                                       mods{k}, local_tf(okK), berM, nbM)]; %#ok<AGROW>
        if ~sigOk; fprintf(2, '      D17 %s: %s\n', mods{k}, sigMsg); end
    end
    report = local_add(report, 'D17_modulation_identity', modOk, strtrim(modDetail));

    % ---------------------------------------------------------------- D18
    % Export contract: the fields the Python bridge (src/simulink_bridge) and
    % experiments/verify_simulink_mat.py read must all be present.
    required = {'iq_samples','tx_iq','noise_iq','interference_iq','time_vector', ...
                'snr_db','ber','bit_errors','bits_compared','modulation', ...
                'interference_power','channel_type','timestamp','sample_rate', ...
                'num_samples','source','seed','noise_seed','run_id','model_version', ...
                'channel_gain_real','channel_gain_imag','measured_snr_db', ...
                'measured_snr_tx_ref_db','measured_sir_db','measured_sinr_db', ...
                'measured_signal_power','measured_noise_power', ...
                'measured_interference_power','checks_passed','snr_definition', ...
                'noise_source'};
    tmpDir = tempname; mkdir(tmpDir);
    cleanupTmp = onCleanup(@() rmdir(tmpDir, 's'));
    try
        f18 = run_simulink_case('QPSK', 10, 0.1, 'AWGN', ...
                  struct('nSamples', N, 'outDir', tmpDir, 'verbose', false, 'name', 'd18'));
        S = load(f18);
        missing = required(~isfield(S, required));
        cplx = ~isreal(S.iq_samples) && ~isreal(S.tx_iq);
        ok18 = isempty(missing) && cplx && S.checks_passed == 1 && ...
               numel(S.iq_samples) == N && strcmp(S.source, 'simulink');
        if isempty(missing); missTxt = 'none'; else; missTxt = strjoin(missing, ', '); end
        d18 = sprintf('missing fields: %s | iq/tx complex %s | checks_passed %d | N %d', ...
                      missTxt, local_tf(cplx), S.checks_passed, numel(S.iq_samples));
    catch err18
        ok18 = false;
        d18  = sprintf('run_simulink_case raised: %s', err18.message);
    end
    report = local_add(report, 'D18_export_contract', ok18, d18);

    local_print(report, verbose);

    nFail = sum(~[report.ok]);
    fprintf('----------------------------------------------------------------\n');
    if nFail == 0
        fprintf(' RESULT: all %d diagnostics PASSED. The PHY is behaving correctly.\n', numel(report));
    else
        fprintf(2, ' RESULT: %d of %d diagnostics FAILED. Do NOT trust measurements yet.\n', ...
                nFail, numel(report));
    end
    fprintf('================================================================\n\n');
end

% ======================================================================= utils

function r = local_sim(modelName, t, tx, snrDb, interfPower, h, Fs, N, noiseSeed)
%LOCAL_SIM  One instrumented simulation with REAL split I/Q inputs.
    if nargin < 9 || isempty(noiseSeed); noiseSeed = 1; end
    assignin('base', 'NoiseSeed',         noiseSeed);
    assignin('base', 'iq_input_i',        [t, real(tx(:))]);
    assignin('base', 'iq_input_q',        [t, imag(tx(:))]);
    assignin('base', 'Fs',                Fs);
    assignin('base', 'SNR_dB',            snrDb);
    assignin('base', 'InterferencePower', interfPower);
    assignin('base', 'ChannelGainRe',     real(h));
    assignin('base', 'ChannelGainIm',     imag(h));
    assignin('base', 'SimStopTime',       (N-1)/Fs);

    set_param(modelName, 'Solver', 'FixedStepDiscrete', ...
                         'FixedStep', '1/Fs', 'StopTime', 'SimStopTime');

    try
        simOut = sim(modelName, 'ReturnWorkspaceOutputs', 'on');
    catch
        simOut = sim(modelName);
    end

    [r.rx, r.t] = local_unpack(local_fetch(simOut, 'rx_iq'));
    r.jam       = local_unpack(local_fetch(simOut, 'interference_signal'));
    r.noise     = local_unpack(local_fetch(simOut, 'noise_signal'));
    r.txEcho    = local_unpack(local_fetch(simOut, 'tx_echo'));
end

function v = local_fetch(simOut, name)
    v = [];
    try
        if isa(simOut, 'Simulink.SimulationOutput')
            if any(strcmp(simOut.who, name)); v = simOut.get(name); end
        elseif isstruct(simOut) && isfield(simOut, name)
            v = simOut.(name);
        end
    catch
        v = [];
    end
    if isempty(v)
        try; v = evalin('base', name); catch; v = []; end
    end
end

function [y, t] = local_unpack(s)
    t = [];
    if isempty(s)
        y = []; return;
    end
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

function [ok, why] = local_check_fw_input(M)
%LOCAL_CHECK_FW_INPUT  Validate a From Workspace array-format input matrix.
%
%   From Workspace's array format requires a REAL matrix [t, data] whose first
%   column is a real, finite, strictly increasing time vector.
%
%   isreal() is evaluated on the WHOLE matrix, never on an extracted column:
%   indexing a complex matrix whose column happens to have a zero imaginary part
%   narrows the result back to real, which would hide the very defect that broke
%   the v2 build.
    ok = true; why = 'real [t, data] matrix, time column strictly increasing';

    if ~isnumeric(M) || ndims(M) ~= 2 || size(M,2) < 2 || size(M,1) < 2
        ok = false; why = sprintf('not a numeric N x >=2 matrix (size %s)', mat2str(size(M))); return;
    end
    if ~isreal(M)
        ok = false; why = 'matrix is COMPLEX - From Workspace array format requires a real matrix'; return;
    end
    tcol = M(:,1);
    if ~isreal(tcol) || any(imag(tcol) ~= 0)
        ok = false; why = 'time column is complex'; return;
    end
    if any(~isfinite(M(:)))
        ok = false; why = 'matrix contains NaN or Inf'; return;
    end
    if any(diff(tcol) <= 0)
        ok = false; why = 'time column is not strictly increasing'; return;
    end
end

function s = local_tf(b)
    if b; s = 'PASS'; else; s = 'FAIL'; end
end

function c = local_corr(a, b)
%LOCAL_CORR  |normalised complex correlation| of two equal-length vectors.
    a = a(:); b = b(:);
    c = abs(a' * b) / sqrt(max(a'*a, realmin) * max(b'*b, realmin));
end

function report = local_add(report, name, ok, detail)
    report(end+1) = struct('name', name, 'ok', logical(ok), 'detail', detail); %#ok<AGROW>
end

function local_print(report, verbose)
    if ~verbose; return; end
    fprintf('\n');
    for i = 1:numel(report)
        if report(i).ok; tag = 'PASS'; else; tag = 'FAIL'; end
        fprintf(' [%s] %-32s %s\n', tag, report(i).name, report(i).detail);
    end
end
