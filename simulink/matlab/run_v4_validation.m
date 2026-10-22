function logDir = run_v4_validation(noiseSource)
%RUN_V4_VALIDATION  Rebuild the v4 PHY model and run every validation step, logged.
%
%   logDir = RUN_V4_VALIDATION()                       % Random Number block noise (default)
%   logDir = RUN_V4_VALIDATION('block_rng')            % rng() inside PHY_Channel instead
%
%   Steps, each in its own try/catch so one failure does not hide the rest:
%     0  environment: MATLAB release, Simulink installed and licensed
%     1  PRESERVE: copy simulink/results and cognitwin_sdr_phy.slx to
%        simulink/results_archive/pre_v4_<stamp>/ BEFORE anything is overwritten
%        (run_simulink_case('QPSK',10,0.25,'Rayleigh') rewrites
%        results/sim_qpsk_snr10_int0p25_rayleigh.mat, and run_baseline_tests
%        rewrites every file in results/baseline/)
%     2  create_cognitwin_model         (with the chosen NoiseSource)
%     3  diagnose_simulink_phy          (D1-D18)
%     4  run_simulink_case('QPSK', 10, 0.25, 'Rayleigh')
%     5  run_baseline_tests             (sections 1-7)
%     6  manifest.csv: every MAT under results/, flagged written_this_run 0/1
%        with its model_version / noise_source / run_id, so stale exports are
%        never mistaken for this run's output
%
%   Everything printed goes to simulink/run_logs/<stamp>/matlab_console.log;
%   step status, the D-table and error reports go to status.mat / summary.txt
%   in the same folder. Nothing is reported as passed unless it ran.

    if nargin < 1 || isempty(noiseSource); noiseSource = 'random_number_blocks'; end

    thisDir = fileparts(mfilename('fullpath'));
    simDir  = fileparts(thisDir);
    runStart = now;
    stamp   = datestr(runStart, 'yyyymmdd_HHMMSS');
    logDir  = fullfile(simDir, 'run_logs', stamp);
    mkdir(logDir);

    diary(fullfile(logDir, 'matlab_console.log'));
    diary on;
    cleanupDiary = onCleanup(@() diary('off'));
    addpath(thisDir);

    st = struct('step', {}, 'status', {}, 'detail', {});

    % ------------------------------------------------------------- 0 env
    fprintf('\n=== [0] environment  %s\n', stamp);
    fprintf('MATLAB  : %s\n', version);
    fprintf('Computer: %s\n', computer);
    hasSl  = ~isempty(ver('simulink'));
    licSl  = license('test', 'Simulink');
    fprintf('Simulink installed: %d, licensed: %d\n', hasSl, licSl);
    st = local_add(st, 'environment', hasSl && licSl, ...
        sprintf('%s | Simulink installed %d licensed %d', version, hasSl, licSl));
    if ~(hasSl && licSl)
        local_finish(logDir, st, []);
        error('run_v4_validation:NoSimulink', 'Simulink is not installed or not licensed here.');
    end

    % ------------------------------------------------------------- 1 preserve
    fprintf('\n=== [1] preserve current model and results\n');
    archive = fullfile(simDir, 'results_archive', ['pre_v4_' stamp]);
    try
        mkdir(archive);
        if exist(fullfile(simDir, 'results'), 'dir')
            copyfile(fullfile(simDir, 'results'), fullfile(archive, 'results'));
        end
        if exist(fullfile(simDir, 'cognitwin_sdr_phy.slx'), 'file')
            copyfile(fullfile(simDir, 'cognitwin_sdr_phy.slx'), archive);
        end
        fprintf('archived to %s\n', archive);
        st = local_add(st, 'preserve', true, archive);
    catch err
        st = local_add(st, 'preserve', false, err.message);
        local_finish(logDir, st, []);
        error('run_v4_validation:ArchiveFailed', ...
              'Could not archive the current results (%s). Nothing was overwritten.', err.message);
    end

    % ------------------------------------------------------------- 2 build
    fprintf('\n=== [2] create_cognitwin_model  (NoiseSource = %s)\n', noiseSource);
    try
        if bdIsLoaded('cognitwin_sdr_phy'); close_system('cognitwin_sdr_phy', 0); end
        assignin('base', 'NoiseSource', noiseSource);
        % Quotes in the path (e.g. C:\Users\O'Brien) are doubled so the char
        % literal handed to evalin stays well formed.
        genPath = strrep(fullfile(simDir, 'create_cognitwin_model.m'), '''', '''''');
        evalin('base', sprintf('run(''%s'');', genPath));
        d = dir(fullfile(simDir, 'cognitwin_sdr_phy.slx'));
        st = local_add(st, 'create_cognitwin_model', true, ...
            sprintf('saved %s (%s, %d bytes)', fullfile(simDir, d.name), d.date, d.bytes));
    catch err
        fprintf(2, '%s\n', getReport(err, 'extended', 'hyperlinks', 'off'));
        st = local_add(st, 'create_cognitwin_model', false, getReport(err, 'basic', 'hyperlinks', 'off'));
        local_finish(logDir, st, []);
        return;                                 % nothing below can run without a model
    end

    % ------------------------------------------------------------- 3 diagnose
    fprintf('\n=== [3] diagnose_simulink_phy\n');
    report = [];
    try
        report = diagnose_simulink_phy(true);
        st = local_add(st, 'diagnose_simulink_phy', all([report.ok]), ...
            sprintf('%d of %d diagnostics passed', sum([report.ok]), numel(report)));
    catch err
        fprintf(2, '%s\n', getReport(err, 'extended', 'hyperlinks', 'off'));
        st = local_add(st, 'diagnose_simulink_phy', false, getReport(err, 'basic', 'hyperlinks', 'off'));
    end

    % ------------------------------------------------------------- 4 Rayleigh
    fprintf('\n=== [4] run_simulink_case(''QPSK'', 10, 0.25, ''Rayleigh'')\n');
    try
        [f4, m4] = run_simulink_case('QPSK', 10, 0.25, 'Rayleigh'); %#ok<ASGLU>
        st = local_add(st, 'rayleigh_case', true, ...
            sprintf(['%s | SNR cfg %.2f, tx-ref %.2f, post-fade %.2f dB | SIR %.2f | SINR %.2f | ' ...
                     '|h| %.4f | BER %.6g (%d/%d) | checks_passed %d | noise %s seed %d'], ...
                    f4, m4.snr_db, m4.measured_snr_tx_ref_db, m4.measured_snr_db, ...
                    m4.measured_sir_db, m4.measured_sinr_db, m4.channel_gain_mag, ...
                    m4.ber, m4.bit_errors, m4.bits_compared, m4.checks_passed, ...
                    m4.noise_source, m4.noise_seed));
    catch err
        fprintf(2, '%s\n', getReport(err, 'extended', 'hyperlinks', 'off'));
        st = local_add(st, 'rayleigh_case', false, getReport(err, 'basic', 'hyperlinks', 'off'));
    end

    % ------------------------------------------------------------- 5 baseline
    fprintf('\n=== [5] run_baseline_tests\n');
    try
        res = run_baseline_tests();
        v = {res.verdict};
        st = local_add(st, 'run_baseline_tests', ~any(strcmp(v, 'FAIL')), ...
            sprintf('%d checks, %d PASS, %d FAIL', numel(v), sum(strcmp(v,'PASS')), sum(strcmp(v,'FAIL'))));
    catch err
        fprintf(2, '%s\n', getReport(err, 'extended', 'hyperlinks', 'off'));
        st = local_add(st, 'run_baseline_tests', false, getReport(err, 'basic', 'hyperlinks', 'off'));
    end

    % ------------------------------------------------------------- 6 manifest
    % Which MAT files did THIS run write? Anything older is listed as stale so
    % a pre-v4 export can never be mistaken for a result of this run.
    try
        nNew = local_manifest(fullfile(simDir, 'results'), runStart, logDir);
        st = local_add(st, 'manifest', nNew > 0, ...
            sprintf('%d MAT files written by this run (see manifest.csv)', nNew));
    catch err
        st = local_add(st, 'manifest', false, err.message);
    end

    local_finish(logDir, st, report);
end

function nNew = local_manifest(resultsDir, runStart, logDir)
%LOCAL_MANIFEST  CSV of every MAT under results/: written by this run or stale.
    files = dir(fullfile(resultsDir, '**', '*.mat'));
    fid = fopen(fullfile(logDir, 'manifest.csv'), 'w');
    c = onCleanup(@() fclose(fid));
    fprintf(fid, 'path,bytes,modified,written_this_run,model_version,noise_source,run_id\n');
    nNew = 0;
    for i = 1:numel(files)
        f = fullfile(files(i).folder, files(i).name);
        isNew = files(i).datenum >= runStart;
        nNew = nNew + isNew;
        mv = ''; ns = ''; rid = '';
        try
            w = whos('-file', f);
            vars = {w.name};
            want = intersect({'model_version','noise_source','run_id'}, vars);
            if ~isempty(want)
                S = load(f, want{:});
                if isfield(S,'model_version'); mv  = S.model_version; end
                if isfield(S,'noise_source');  ns  = S.noise_source;  end
                if isfield(S,'run_id');        rid = S.run_id;        end
            end
        catch
            mv = 'UNREADABLE';
        end
        % Path relative to simulink/ with forward slashes, so the manifest still
        % identifies the files after they are copied to another machine.
        prefix = [resultsDir filesep];
        if strncmpi(f, prefix, numel(prefix))
            relPath = ['results/' strrep(f(numel(prefix)+1:end), '\', '/')];
        else
            relPath = strrep(f, '\', '/');      % unexpected layout: keep the full path
        end
        fprintf(fid, '"%s",%d,%s,%d,%s,%s,%s\n', relPath, files(i).bytes, ...
                datestr(files(i).datenum, 'yyyy-mm-ddTHH:MM:SS'), isNew, mv, ns, rid);
    end
end

function st = local_add(st, step, ok, detail)
    if ok; s = 'PASS'; else; s = 'FAIL'; end
    st(end+1) = struct('step', step, 'status', s, 'detail', detail);
    fprintf('>>> %-24s %s  %s\n', step, s, strtok(detail, newline));
end

function local_finish(logDir, st, report)
    save(fullfile(logDir, 'status.mat'), 'st', 'report');
    fid = fopen(fullfile(logDir, 'summary.txt'), 'w');
    if fid < 0; return; end
    c = onCleanup(@() fclose(fid));
    fprintf(fid, 'run_v4_validation  %s\nMATLAB %s\n\nSTEPS\n', logDir, version);
    for i = 1:numel(st)
        fprintf(fid, '  %-24s %s\n      %s\n', st(i).step, st(i).status, ...
                strrep(st(i).detail, newline, [newline '      ']));
    end
    if ~isempty(report)
        fprintf(fid, '\nDIAGNOSTICS\n');
        for i = 1:numel(report)
            if report(i).ok; s = 'PASS'; else; s = 'FAIL'; end
            fprintf(fid, '  [%s] %-36s %s\n', s, report(i).name, report(i).detail);
        end
    end
    fprintf(fid, ['\nNEXT (from the repository root):\n' ...
                  '  python experiments/verify_simulink_mat.py --dir simulink/results/baseline\n' ...
                  '  python experiments/verify_simulink_mat.py --mat simulink/results/sim_qpsk_snr10_int0p25_rayleigh.mat\n' ...
                  '  python experiments/handoff_check.py post\n' ...
                  '  python -m pytest -q\n']);
    fprintf('\nLogs: %s\n', logDir);
end
