function loop = run_simulink_closed_loop(opts)
%RUN_SIMULINK_CLOSED_LOOP  Simulink PHY in the loop with the Python agents + ACWRA.
%
%   loop = RUN_SIMULINK_CLOSED_LOOP(opts)
%
%   Step k: run_simulink_case() simulates the modulation chosen at step k-1 under
%   the step-k channel conditions and exports a MAT file; MATLAB then calls
%       python experiments/acwra_decide.py --mat <export> --state <json> --out <json>
%   which validates the export, runs the existing Spectrum Agent -> Digital Twin ->
%   Prediction Agent -> Cyber Defense Agent -> ACWRA pipeline (twin history carried
%   across steps in the state file) and returns the next modulation. One-step
%   actuation delay: the decision from step k is applied at step k+1.
%
%   opts fields (defaults):
%       .snrDb          [20 20 20 12 12 12 6 6 6 6]   per-step SNR (dB)
%       .interference   [0 0 0 0 0.1 0.1 0.3 0.3 0.3 0.3]  per-step jammer power
%       .channel        'AWGN'          'AWGN' | 'Rayleigh' | 'Rician'
%       .initialMod     'QPSK'
%       .seed           100             step k uses seed + k
%       .nSamples       10000
%       .python         'python'        interpreter that has requirements.txt installed
%       .outDir         simulink/results/closed_loop/<stamp>/
%
%   Writes into outDir: step_###.mat (exports), decision_###.json, twin_state.json,
%   loop_log.csv (one row per step) and console.log. Nothing outside outDir is
%   modified. Requires the v4 model (run_v4_validation first).
%
%   STATUS: written without MATLAB available; static checks only until executed.

    if nargin < 1; opts = struct(); end
    def = struct('snrDb', [20 20 20 12 12 12 6 6 6 6], ...
                 'interference', [0 0 0 0 0.1 0.1 0.3 0.3 0.3 0.3], ...
                 'channel', 'AWGN', 'initialMod', 'QPSK', 'seed', 100, ...
                 'nSamples', 10000, 'python', 'python', 'outDir', '');
    f = fieldnames(def);
    for i = 1:numel(f)
        if ~isfield(opts, f{i}) || isempty(opts.(f{i})); opts.(f{i}) = def.(f{i}); end
    end
    if numel(opts.snrDb) ~= numel(opts.interference)
        error('run_simulink_closed_loop:BadSchedule', 'snrDb and interference must have the same length.');
    end

    thisDir  = fileparts(mfilename('fullpath'));
    simDir   = fileparts(thisDir);
    repoRoot = fileparts(simDir);
    decide   = fullfile(repoRoot, 'experiments', 'acwra_decide.py');
    if ~exist(decide, 'file')
        error('run_simulink_closed_loop:NoDecider', 'Python decision script not found: %s', decide);
    end
    if isempty(opts.outDir)
        opts.outDir = fullfile(simDir, 'results', 'closed_loop', datestr(now, 'yyyymmdd_HHMMSS'));
    end
    if ~exist(opts.outDir, 'dir'); mkdir(opts.outDir); end
    addpath(thisDir);
    diary(fullfile(opts.outDir, 'console.log')); diary on;
    cleanupDiary = onCleanup(@() diary('off'));

    stateFile = fullfile(opts.outDir, 'twin_state.json');
    logFile   = fullfile(opts.outDir, 'loop_log.csv');
    fid = fopen(logFile, 'w');
    cleanupLog = onCleanup(@() fclose(fid));
    fprintf(fid, ['step,snr_db,interference,channel,modulation_applied,ber,bit_errors,bits_compared,' ...
                  'measured_sinr_db,checks_passed,selected_strategy,next_modulation,expected_utility,' ...
                  'risk_score,provenance,decision_status\n']);

    nSteps   = numel(opts.snrDb);
    stepDur  = opts.nSamples / 100e3;               % run_simulink_case default Fs = 100 kHz
    current  = opts.initialMod;
    loop     = struct('step', {}, 'modulation', {}, 'ber', {}, 'next', {}, 'status', {});

    for k = 1:nSteps
        name = sprintf('step_%03d', k);
        fprintf('\n=== closed loop step %d/%d: %s, SNR %.1f dB, J %.3g, %s\n', ...
                k, nSteps, current, opts.snrDb(k), opts.interference(k), opts.channel);
        try
            [matFile, m] = run_simulink_case(current, opts.snrDb(k), opts.interference(k), opts.channel, ...
                struct('seed', opts.seed + k, 'nSamples', opts.nSamples, 'outDir', opts.outDir, ...
                       'name', name, 'timestamp', (k-1) * stepDur, 'verbose', false));
        catch err
            fprintf(2, 'step %d simulation failed: %s\n', k, err.message);
            fprintf(fid, '%d,%g,%g,%s,%s,,,,,,,,,,,SIMULATION_FAILED\n', k, opts.snrDb(k), ...
                    opts.interference(k), opts.channel, current);
            loop(end+1) = struct('step', k, 'modulation', current, 'ber', NaN, 'next', current, ...
                                 'status', 'SIMULATION_FAILED'); %#ok<AGROW>
            break;                                   % no valid measurement -> no decision
        end

        decFile = fullfile(opts.outDir, sprintf('decision_%03d.json', k));
        cmd = sprintf('"%s" "%s" --mat "%s" --state "%s" --out "%s" --require-real', ...
                      opts.python, decide, matFile, stateFile, decFile);
        [rc, txt] = system(cmd);
        fprintf('%s\n', txt);
        if rc ~= 0 || ~exist(decFile, 'file')
            fprintf(2, 'step %d: decision failed (exit %d)\n', k, rc);
            fprintf(fid, '%d,%g,%g,%s,%s,%g,%d,%d,%g,%d,,,,,,DECISION_FAILED\n', k, opts.snrDb(k), ...
                    opts.interference(k), opts.channel, current, m.ber, m.bit_errors, m.bits_compared, ...
                    m.measured_sinr_db, m.checks_passed);
            loop(end+1) = struct('step', k, 'modulation', current, 'ber', m.ber, 'next', current, ...
                                 'status', 'DECISION_FAILED'); %#ok<AGROW>
            break;                                   % never invent a decision
        end
        d = jsondecode(fileread(decFile));
        fprintf(fid, '%d,%g,%g,%s,%s,%g,%d,%d,%g,%d,%s,%s,%g,%g,%s,OK\n', k, opts.snrDb(k), ...
                opts.interference(k), opts.channel, current, m.ber, m.bit_errors, m.bits_compared, ...
                m.measured_sinr_db, m.checks_passed, d.selected_strategy, d.next_modulation, ...
                d.expected_utility, d.risk_score, d.provenance);
        loop(end+1) = struct('step', k, 'modulation', current, 'ber', m.ber, ...
                             'next', d.next_modulation, 'status', 'OK'); %#ok<AGROW>
        current = d.next_modulation;                 % applied at step k+1
    end
    fprintf('\nClosed-loop log: %s\n', logFile);
end
