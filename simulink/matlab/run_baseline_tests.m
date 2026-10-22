function results = run_baseline_tests(opts)
%RUN_BASELINE_TESTS  PHY acceptance suite for the CogniTwin-SDR Simulink model.
%
%   results = RUN_BASELINE_TESTS(opts)
%
%   ACCEPTANCE CRITERIA ARE FIXED BEFORE ANY TEST RUNS (see local_criteria below),
%   so a result cannot be rationalised after the fact.
%
%   Sections
%     1  baseline cases A-F                       (QPSK, AWGN/Rayleigh, P = 0..1)
%     2  SNR ladder, multiple seeds               (BER must fall as SNR rises)
%     3  interference sweep P = 0.01 .. 10        (SIR must track -10log10(P))
%     4  monotonicity of SINR vs interference
%     5  multi-seed repeatability for AWGN and Rayleigh
%     6  modulation coverage: BPSK and OFDM-QPSK, AWGN ladder + Rayleigh
%     7  noise independence across seeds (the v3 build reused ONE realisation)
%
%   Every number is measured from the logged arrays by run_simulink_case, which
%   refuses to export a run that fails its physical-consistency battery.
%
%   Theoretical reference used for BER (coherent, Gray mapped, matched to the
%   constellations in cognitwin_waveform), with SINR = |h|^2 P_tx/(P_noise+P_jam)
%   measured from the arrays and Q(x) = 0.5*erfc(x/sqrt(2)):
%
%       QPSK, OFDM-QPSK   BER = Q( sqrt(SINR) )      (Es = 2 Eb, noise split I/Q)
%       BPSK              BER = Q( sqrt(2*SINR) )    (only the I noise matters)
%
%   OFDM-QPSK uses the QPSK expression because the unitary FFT preserves the
%   per-subcarrier SINR; the cyclic prefix is discarded, not combined.
%   The jammer is complex Gaussian, so it adds to the noise in the same form.
%
%   Results are written to simulink/results/baseline/ as a MAT file and a CSV.

    if nargin < 1; opts = struct(); end
    if ~isfield(opts,'nSamples') || isempty(opts.nSamples); opts.nSamples = 10000; end
    if ~isfield(opts,'seeds')    || isempty(opts.seeds);    opts.seeds    = [11 23 37]; end
    if ~isfield(opts,'quick')    || isempty(opts.quick);    opts.quick    = false; end

    thisDir     = fileparts(mfilename('fullpath'));
    simulinkDir = fileparts(thisDir);
    outDir      = fullfile(simulinkDir, 'results', 'baseline');
    if ~exist(outDir,'dir'); mkdir(outDir); end

    crit = local_criteria();

    fprintf('\n==========================================================================\n');
    fprintf(' COGNITWIN-SDR PHY BASELINE ACCEPTANCE SUITE\n');
    fprintf('==========================================================================\n');
    fprintf(' Samples per run : %d\n', opts.nSamples);
    fprintf(' Seeds           : %s\n', mat2str(opts.seeds));
    fprintf(' ACCEPTANCE CRITERIA (fixed before running):\n');
    fn = fieldnames(crit);
    for i = 1:numel(fn)
        fprintf('   %-28s %s\n', fn{i}, crit.(fn{i}));
    end
    fprintf('--------------------------------------------------------------------------\n');

    results = struct('id',{},'section',{},'modulation',{},'snr_db',{},'interference',{}, ...
                     'channel',{},'seed',{},'h_mag',{},'p_sig',{},'p_noise',{},'p_jam',{}, ...
                     'p_rx',{},'snr_meas',{},'sir_meas',{},'sinr_meas',{},'ber',{}, ...
                     'ber_theory',{},'n_samples',{},'verdict',{},'reason',{});

    ro = struct('nSamples', opts.nSamples, 'outDir', outDir, 'verbose', false, 'strict', true);

    % =====================================================================
    % SECTION 1 - baseline cases A .. F
    % =====================================================================
    fprintf('\n[SECTION 1] Baseline cases A-F\n');
    cases = { ...
        'A', 'QPSK', 10, 0.00, 'AWGN'     ; ...
        'B', 'QPSK', 20, 0.00, 'AWGN'     ; ...
        'C', 'QPSK', 10, 0.00, 'Rayleigh' ; ...
        'D', 'QPSK', 10, 0.25, 'Rayleigh' ; ...
        'E', 'QPSK', 10, 0.50, 'Rayleigh' ; ...
        'F', 'QPSK', 10, 1.00, 'Rayleigh' };

    berA = NaN; berB = NaN;
    for i = 1:size(cases,1)
        c = cases(i,:);
        o = ro; o.seed = opts.seeds(1); o.name = sprintf('baseline_%s', c{1});
        rec = local_run(c{2}, c{3}, c{4}, c{5}, o, sprintf('1%s', c{1}), 'A-F baseline');
        [rec.verdict, rec.reason] = local_judge_case(rec, crit);
        results(end+1) = rec; %#ok<AGROW>
        local_report_row(rec);
        if strcmp(c{1},'A'); berA = rec.ber; end
        if strcmp(c{1},'B'); berB = rec.ber; end
    end

    % explicit AWGN SNR-ordering check demanded by the task
    ordOk = isfinite(berA) && isfinite(berB) && berB < berA;
    fprintf('  >> AWGN SNR ordering: BER(20 dB) = %.6g  <  BER(10 dB) = %.6g   : %s\n', ...
            berB, berA, local_tf(ordOk));
    results(end+1) = local_meta('1ORD', 'A-F baseline', ordOk, ...
        sprintf('BER(20 dB)=%.6g must be < BER(10 dB)=%.6g', berB, berA));

    notHalf = isfinite(berA) && berA < crit_num(crit.awgn_ber_not_half);
    fprintf('  >> AWGN zero-interference BER is not ~0.5: BER = %.6g   : %s\n', ...
            berA, local_tf(notHalf));
    results(end+1) = local_meta('1HALF', 'A-F baseline', notHalf, ...
        sprintf('BER(10 dB, AWGN, P=0)=%.6g must be < 0.05', berA));

    % =====================================================================
    % SECTION 2 - SNR ladder across seeds
    % =====================================================================
    fprintf('\n[SECTION 2] SNR ladder (AWGN, P = 0) across %d seeds\n', numel(opts.seeds));
    snrLadder = [0 5 10 15 20];
    if opts.quick; snrLadder = [0 10 20]; end

    for s = 1:numel(opts.seeds)
        bers = nan(1, numel(snrLadder));
        for k = 1:numel(snrLadder)
            o = ro; o.seed = opts.seeds(s);
            o.name = sprintf('ladder_seed%d_snr%d', opts.seeds(s), snrLadder(k));
            rec = local_run('QPSK', snrLadder(k), 0, 'AWGN', o, ...
                            sprintf('2S%dK%d', s, k), 'SNR ladder');
            [rec.verdict, rec.reason] = local_judge_case(rec, crit);
            results(end+1) = rec; %#ok<AGROW>
            local_report_row(rec);
            bers(k) = rec.ber;
        end
        mono = all(diff(bers) <= 1e-9);
        fprintf('  >> seed %d BER monotonically non-increasing with SNR: %s   [%s]\n', ...
                opts.seeds(s), local_tf(mono), num2str(bers, '%.5g  '));
        results(end+1) = local_meta(sprintf('2MONO%d', s), 'SNR ladder', mono, ...
            sprintf('BER vs SNR must be non-increasing: %s', mat2str(bers, 4)));
    end

    % =====================================================================
    % SECTION 3 - interference sweep (AWGN so |h| = 1 exactly)
    % =====================================================================
    fprintf('\n[SECTION 3] Interference sweep, AWGN, SNR = 40 dB (noise floor negligible)\n');
    pList = [0.01 0.1 0.25 0.5 1 2 4 10];
    sinrList = nan(1, numel(pList));

    for k = 1:numel(pList)
        o = ro; o.seed = opts.seeds(1);
        o.name = sprintf('interf_p%s', strrep(sprintf('%g',pList(k)),'.','p'));
        rec = local_run('QPSK', 40, pList(k), 'AWGN', o, sprintf('3P%d',k), 'interference sweep');
        expSir = -10*log10(pList(k));
        err = abs(rec.sir_meas - expSir);
        ok = err < crit_num(crit.sir_tolerance_db);
        rec.verdict = local_tf(ok);
        rec.reason  = sprintf('measured SIR %.3f dB vs expected -10log10(%g) = %.3f dB (err %.3f dB)', ...
                              rec.sir_meas, pList(k), expSir, err);
        results(end+1) = rec; %#ok<AGROW>
        sinrList(k) = rec.sinr_meas;
        fprintf('  P = %-6g  P_jam_meas = %-9.5f  SIR = %8.3f dB (expected %8.3f)  SINR = %8.3f dB  BER = %.6f  : %s\n', ...
                pList(k), rec.p_jam, rec.sir_meas, expSir, rec.sinr_meas, rec.ber, rec.verdict);
    end

    % =====================================================================
    % SECTION 4 - SINR monotonicity
    % =====================================================================
    monoSinr = all(diff(sinrList) < 0);
    fprintf('\n[SECTION 4] SINR strictly decreasing as interference rises: %s\n', local_tf(monoSinr));
    fprintf('            %s\n', num2str(sinrList, '%8.2f'));
    results(end+1) = local_meta('4MONO', 'SINR monotonicity', monoSinr, ...
        sprintf('SINR must strictly decrease across P = %s', mat2str(pList)));

    % =====================================================================
    % SECTION 5 - multi-seed repeatability
    % =====================================================================
    seedNoise = cell(1, numel(opts.seeds));
    fprintf('\n[SECTION 5] Multi-seed repeatability (QPSK, SNR = 10 dB, P = 0)\n');
    for chanIdx = 1:2
        chans = {'AWGN','Rayleigh'};
        ch = chans{chanIdx};
        vals = nan(1, numel(opts.seeds));
        for s = 1:numel(opts.seeds)
            o = ro; o.seed = opts.seeds(s);
            o.name = sprintf('seedrep_%s_%d', lower(ch), opts.seeds(s));
            [rec, mSeed] = local_run('QPSK', 10, 0, ch, o, sprintf('5%s%d', ch(1), s), 'multi-seed');
            if chanIdx == 1
                seedNoise{s} = mSeed.noise_iq; %#ok<AGROW>
            end
            [rec.verdict, rec.reason] = local_judge_case(rec, crit);
            results(end+1) = rec; %#ok<AGROW>
            local_report_row(rec);
            vals(s) = rec.ber;
        end
        allOk = all(strcmp({results(end-numel(opts.seeds)+1:end).verdict}, 'PASS'));
        fprintf('  >> %-8s every seed within theory: %s   BERs = [%s]\n', ...
                ch, local_tf(allOk), num2str(vals, '%.5g  '));
    end

    % =====================================================================
    % SECTION 6 - modulation coverage (BPSK, OFDM-QPSK)
    % =====================================================================
    fprintf('\n[SECTION 6] Modulation coverage: BPSK and OFDM-QPSK\n');
    covMods = {'BPSK', 'OFDM-QPSK'};
    covSnr  = [0 5 10];
    for i = 1:numel(covMods)
        bers = nan(1, numel(covSnr));
        for k = 1:numel(covSnr)
            o = ro; o.seed = opts.seeds(1);
            o.name = sprintf('mod_%s_snr%d_awgn', lower(strrep(covMods{i},'-','')), covSnr(k));
            rec = local_run(covMods{i}, covSnr(k), 0, 'AWGN', o, ...
                            sprintf('6M%dK%d', i, k), 'modulation coverage');
            [rec.verdict, rec.reason] = local_judge_case(rec, crit);
            results(end+1) = rec; %#ok<AGROW>
            local_report_row(rec);
            bers(k) = rec.ber;
        end
        mono = all(diff(bers) <= 1e-9);
        results(end+1) = local_meta(sprintf('6MONO%d', i), 'modulation coverage', mono, ...
            sprintf('%s BER vs SNR must be non-increasing: %s', covMods{i}, mat2str(bers, 4))); %#ok<AGROW>

        o = ro; o.seed = opts.seeds(1);
        o.name = sprintf('mod_%s_snr10_rayleigh', lower(strrep(covMods{i},'-','')));
        rec = local_run(covMods{i}, 10, 0, 'Rayleigh', o, sprintf('6M%dR', i), 'modulation coverage');
        [rec.verdict, rec.reason] = local_judge_case(rec, crit);
        results(end+1) = rec; %#ok<AGROW>
        local_report_row(rec);
    end

    % =====================================================================
    % SECTION 7 - noise independence across seeds
    % =====================================================================
    % The v3 model ignored every seed: noise_iq was bit-identical for seeds
    % 11, 23 and 37. Different seeds must now give uncorrelated noise.
    fprintf('\n[SECTION 7] Noise independence across seeds (AWGN runs of section 5)\n');
    thr = crit_num(crit.noise_seed_corr) / sqrt(opts.nSamples);
    for a = 1:numel(seedNoise)
        for b = a+1:numel(seedNoise)
            na = seedNoise{a}; nb = seedNoise{b};
            c  = abs(na' * nb) / sqrt((na'*na) * (nb'*nb));
            ok = c < thr;
            fprintf('  seeds %d vs %d : |corr(noise)| = %.5f (threshold %.5f) : %s\n', ...
                    opts.seeds(a), opts.seeds(b), c, thr, local_tf(ok));
            results(end+1) = local_meta(sprintf('7N%d%d', a, b), 'noise independence', ok, ...
                sprintf('|corr(noise seed %d, noise seed %d)| = %.5f must be < %.5f', ...
                        opts.seeds(a), opts.seeds(b), c, thr)); %#ok<AGROW>
        end
    end

    % =====================================================================
    % SUMMARY + EXPORT
    % =====================================================================
    verdicts = {results.verdict};
    nPass = sum(strcmp(verdicts,'PASS'));
    nFail = sum(strcmp(verdicts,'FAIL'));

    fprintf('\n==========================================================================\n');
    fprintf(' SUMMARY: %d checks, %d PASS, %d FAIL\n', numel(results), nPass, nFail);
    if nFail > 0
        fprintf(2, ' FAILURES:\n');
        for i = 1:numel(results)
            if strcmp(results(i).verdict,'FAIL')
                fprintf(2, '   %-8s %-22s %s\n', results(i).id, results(i).section, results(i).reason);
            end
        end
    end
    fprintf('==========================================================================\n');

    matFile = fullfile(outDir, 'baseline_results.mat');
    save(matFile, 'results', 'crit');
    csvFile = fullfile(outDir, 'baseline_results.csv');
    local_write_csv(csvFile, results);
    fprintf(' Results : %s\n         : %s\n', matFile, csvFile);
    fprintf(' Next    : python experiments/verify_simulink_mat.py --dir simulink/results/baseline\n\n');
end

% ================================================================ criteria

function crit = local_criteria()
%LOCAL_CRITERIA  Fixed BEFORE any test is executed.
    crit.ber_vs_theory_abs   = '1.5e-3  : |BER_measured - BER_theory| tolerance (absolute)';
    crit.ber_vs_theory_rel   = '0.35    : relative tolerance when BER_theory > 0.005';
    crit.awgn_ber_not_half   = '0.05    : AWGN SNR=10 dB P=0 BER must be far below 0.5';
    crit.snr_tolerance_db    = '0.5     : |measured SNR - 10log10(P_sig/P_noise)| from arrays';
    crit.sir_tolerance_db    = '0.5     : |measured SIR - (-10log10(P))| for unit-power tx';
    crit.sinr_monotonic      = 'strict  : SINR must decrease as interference increases';
    crit.ber_monotonic       = 'non-inc : BER must not increase as SNR increases';
    crit.noise_seed_corr     = '5       : |corr(noise_a, noise_b)| < 5/sqrt(N) for different seeds';
end

function v = crit_num(s)
    tok = regexp(s, '^\s*([0-9.eE+-]+)', 'tokens', 'once');
    if isempty(tok); v = NaN; else; v = str2double(tok{1}); end
end

% ================================================================ helpers

function [rec, m] = local_run(mod, snr, P, chan, o, id, section)
    [~, m] = run_simulink_case(mod, snr, P, chan, o);
    rec = struct();
    rec.id           = id;
    rec.section      = section;
    rec.modulation   = mod;
    rec.snr_db       = snr;
    rec.interference = P;
    rec.channel      = chan;
    rec.seed         = o.seed;
    rec.h_mag        = m.channel_gain_mag;
    rec.p_sig        = m.measured_signal_power;
    rec.p_noise      = m.measured_noise_power;
    rec.p_jam        = m.measured_interference_power;
    rec.p_rx         = m.measured_power;
    rec.snr_meas     = m.measured_snr_db;
    rec.sir_meas     = m.measured_sir_db;
    rec.sinr_meas    = m.measured_sinr_db;
    rec.ber          = m.ber;
    rec.n_samples    = m.num_samples;
    % coherent theory at the MEASURED SINR
    sinrLin = rec.p_sig / max(rec.p_noise + rec.p_jam, realmin);
    rec.ber_theory = local_ber_theory(mod, sinrLin);
    rec.verdict = '';
    rec.reason  = '';
end

function b = local_ber_theory(mod, sinrLin)
%LOCAL_BER_THEORY  Coherent Gray-mapped BER at a given linear SINR.
    switch upper(strtrim(mod))
        case 'BPSK'
            b = 0.5*erfc(sqrt(2*sinrLin)/sqrt(2));
        otherwise                                   % QPSK, OFDM-QPSK
            b = 0.5*erfc(sqrt(sinrLin)/sqrt(2));
    end
end

function [verdict, reason] = local_judge_case(rec, crit)
    absTol = crit_num(crit.ber_vs_theory_abs);
    relTol = crit_num(crit.ber_vs_theory_rel);
    d = abs(rec.ber - rec.ber_theory);
    if rec.ber_theory > 0.005
        ok = d <= relTol * rec.ber_theory;
        reason = sprintf('BER %.6g vs theory %.6g (rel err %.3f, tol %.2f)', ...
                         rec.ber, rec.ber_theory, d/max(rec.ber_theory,realmin), relTol);
    else
        ok = d <= absTol;
        reason = sprintf('BER %.6g vs theory %.6g (abs err %.3g, tol %.3g)', ...
                         rec.ber, rec.ber_theory, d, absTol);
    end
    verdict = local_tf(ok);
end

function rec = local_meta(id, section, ok, reason)
    rec = struct('id',id,'section',section,'modulation','-','snr_db',NaN, ...
                 'interference',NaN,'channel','-','seed',NaN,'h_mag',NaN, ...
                 'p_sig',NaN,'p_noise',NaN,'p_jam',NaN,'p_rx',NaN, ...
                 'snr_meas',NaN,'sir_meas',NaN,'sinr_meas',NaN,'ber',NaN, ...
                 'ber_theory',NaN,'n_samples',NaN, ...
                 'verdict',local_tf(ok),'reason',reason);
end

function local_report_row(rec)
    fprintf(['  %-6s %-10s SNR %5.1f  P %-5g %-9s |h| %.4f | P_sig %.4f P_n %.5f P_j %.5f | ' ...
             'SNR %6.2f SIR %7.2f SINR %6.2f dB | BER %.6f (theory %.6f) : %s\n'], ...
            rec.id, rec.modulation, rec.snr_db, rec.interference, rec.channel, rec.h_mag, ...
            rec.p_sig, rec.p_noise, rec.p_jam, rec.snr_meas, rec.sir_meas, rec.sinr_meas, ...
            rec.ber, rec.ber_theory, rec.verdict);
end

function s = local_tf(b)
    if b; s = 'PASS'; else; s = 'FAIL'; end
end

function local_write_csv(path, results)
    fid = fopen(path, 'w');
    if fid < 0; warning('Could not write %s', path); return; end
    fprintf(fid, ['id,section,modulation,snr_db,interference,channel,seed,h_mag,' ...
                  'p_sig,p_noise,p_jam,p_rx,snr_meas_db,sir_meas_db,sinr_meas_db,' ...
                  'ber,ber_theory,n_samples,verdict,reason\n']);
    for i = 1:numel(results)
        r = results(i);
        fprintf(fid, '%s,%s,%s,%g,%g,%s,%g,%g,%g,%g,%g,%g,%g,%g,%g,%g,%g,%g,%s,"%s"\n', ...
                r.id, r.section, r.modulation, r.snr_db, r.interference, r.channel, r.seed, ...
                r.h_mag, r.p_sig, r.p_noise, r.p_jam, r.p_rx, r.snr_meas, r.sir_meas, ...
                r.sinr_meas, r.ber, r.ber_theory, r.n_samples, r.verdict, r.reason);
    end
    fclose(fid);
end
