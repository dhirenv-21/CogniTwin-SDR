function files = run_simulink_campaign(which, opts)
%RUN_SIMULINK_CAMPAIGN  Batch the Task 11 Part 9 validation matrix through Simulink.
%
%   files = RUN_SIMULINK_CAMPAIGN(which, opts)
%
%   which (char, default 'all'):
%       'modulation'   BPSK / QPSK / OFDM-QPSK at a nominal operating point   (Part 9-B)
%       'snr'          SNR sweep -20..40 dB                                    (Part 9-C)
%       'interference' interference sweep 0..10                                (Part 9-D)
%       'channel'      AWGN vs Rayleigh vs Rician                              (Part 9-E)
%       'stress'       SNR x interference x modulation matrix                  (Part 9-F)
%       'quick'        modulation + a short SNR sweep (fast smoke test)
%       'all'          everything above
%
%   opts is forwarded to run_simulink_case (see its help). Useful fields:
%       .nSamples (default 10000), .Fs, .seed, .outDir
%
%   Output MAT files land in simulink/results/campaign/ and are consumed by
%       python experiments/simulink_acwra_campaign.py --source matlab
%
%   EXAMPLE
%       cd simulink/matlab
%       run_simulink_campaign('all');

    if nargin < 1 || isempty(which); which = 'all'; end
    if nargin < 2; opts = struct(); end

    thisDir     = fileparts(mfilename('fullpath'));
    simulinkDir = fileparts(thisDir);
    if ~isfield(opts,'outDir') || isempty(opts.outDir)
        opts.outDir = fullfile(simulinkDir, 'results', 'campaign');
    end
    if ~exist(opts.outDir,'dir'); mkdir(opts.outDir); end
    if ~isfield(opts,'nSamples') || isempty(opts.nSamples); opts.nSamples = 10000; end
    if ~isfield(opts,'seed')     || isempty(opts.seed);     opts.seed     = 42;    end

    which = lower(strtrim(which));
    cases = {};

    modulations   = {'BPSK','QPSK','OFDM-QPSK'};
    snrList       = [-20 -10 -5 0 3 5 8 10 15 20 25 30 40];
    interfList    = [0 0.0001 0.001 0.01 0.05 0.1 0.25 0.5 1 2 2.5 4 10];
    channels      = {'AWGN','Rayleigh'};
    stressSnr     = [3 5 8 10 20];
    stressInterf  = [0 0.1 0.25 0.5 1 2.5];

    doAll = strcmp(which,'all');

    % ---- B. modulation ---------------------------------------------------
    if doAll || any(strcmp(which,{'modulation','quick'}))
        for i = 1:numel(modulations)
            cases{end+1} = struct('mod',modulations{i},'snr',10,'int',0.0,'chan','AWGN', ...
                                  'group','B_modulation'); %#ok<AGROW>
        end
    end

    % ---- C. SNR sweep ----------------------------------------------------
    if doAll || strcmp(which,'snr')
        for s = snrList
            cases{end+1} = struct('mod','QPSK','snr',s,'int',0.0,'chan','AWGN', ...
                                  'group','C_snr'); %#ok<AGROW>
        end
    elseif strcmp(which,'quick')
        for s = [0 10 20]
            cases{end+1} = struct('mod','QPSK','snr',s,'int',0.0,'chan','AWGN', ...
                                  'group','C_snr'); %#ok<AGROW>
        end
    end

    % ---- D. interference sweep ------------------------------------------
    if doAll || strcmp(which,'interference')
        for p = interfList
            cases{end+1} = struct('mod','QPSK','snr',30,'int',p,'chan','AWGN', ...
                                  'group','D_interference'); %#ok<AGROW>
        end
    end

    % ---- E. channel ------------------------------------------------------
    if doAll || strcmp(which,'channel')
        for c = 1:numel(channels)
            for m = 1:numel(modulations)
                cases{end+1} = struct('mod',modulations{m},'snr',10,'int',0.0, ...
                                      'chan',channels{c},'group','E_channel'); %#ok<AGROW>
            end
        end
    end

    % ---- F. stress matrix ------------------------------------------------
    if doAll || strcmp(which,'stress')
        for m = 1:numel(modulations)
            for s = stressSnr
                for p = stressInterf
                    cases{end+1} = struct('mod',modulations{m},'snr',s,'int',p, ...
                                          'chan','AWGN','group','F_stress'); %#ok<AGROW>
                end
            end
        end
    end

    if isempty(cases)
        error('run_simulink_campaign:UnknownSet', ...
              'Unknown campaign set "%s".', which);
    end

    fprintf('\n=============================================================\n');
    fprintf(' COGNITWIN-SDR SIMULINK CAMPAIGN: %s  (%d cases)\n', upper(which), numel(cases));
    fprintf(' Output: %s\n', opts.outDir);
    fprintf('=============================================================\n');

    files = cell(numel(cases),1);
    nFail = 0;
    tAll = tic;

    for i = 1:numel(cases)
        c = cases{i};
        o = opts;
        o.seed = opts.seed + i;
        o.verbose = false;
        o.name = sprintf('%s_%03d_%s_snr%s_int%s_%s', c.group, i, ...
                         lower(strrep(c.mod,'-','')), ...
                         local_tag(c.snr), local_tag(c.int), lower(c.chan));
        try
            files{i} = run_simulink_case(c.mod, c.snr, c.int, c.chan, o);
            fprintf('  [%3d/%3d] OK   %-10s SNR %6.1f  int %-7g %-9s -> %s\n', ...
                    i, numel(cases), c.mod, c.snr, c.int, c.chan, ...
                    local_basename(files{i}));
        catch err
            nFail = nFail + 1;
            files{i} = '';
            fprintf(2,'  [%3d/%3d] FAIL %-10s SNR %6.1f  int %-7g %-9s : %s\n', ...
                    i, numel(cases), c.mod, c.snr, c.int, c.chan, err.message);
        end
    end

    files = files(~cellfun(@isempty, files));

    fprintf('-------------------------------------------------------------\n');
    fprintf(' Completed %d/%d cases (%d failed) in %.1f s\n', ...
            numel(files), numel(cases), nFail, toc(tAll));
    fprintf(' Next:  python experiments/simulink_acwra_campaign.py --source matlab\n');
    fprintf('=============================================================\n');
end

function tag = local_tag(x)
    tag = strrep(strrep(sprintf('%g', x), '.', 'p'), '-', 'm');
end

function b = local_basename(p)
    [~, n, e] = fileparts(p);
    b = [n e];
end
