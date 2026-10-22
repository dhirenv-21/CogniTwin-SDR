function outFile = run_simulink_case(modulation, snrDb, interferencePower, channelType, opts)
%RUN_SIMULINK_CASE  Run ONE real Simulink PHY simulation and export it for Python.
%
%   outFile = RUN_SIMULINK_CASE(modulation, snrDb, interferencePower, channelType, opts)
%
%   This is the MATLAB half of the Task 11 end-to-end path. It
%     1. builds a user-selectable baseband waveform (BPSK / QPSK / OFDM-QPSK),
%     2. drives it through the REAL cognitwin_sdr_phy.slx model,
%     3. measures the received I/Q, the true BER and the channel gain,
%     4. exports a MAT file that experiments/simulink_acwra_demo.py can ingest.
%
%   Arguments (all optional, shown with defaults):
%       modulation        'QPSK'      'BPSK' | 'QPSK' | 'OFDM-QPSK'
%       snrDb             20          channel SNR in dB
%       interferencePower 0           jammer power (signal power is normalised to 1,
%                                     so SIR_dB = -10*log10(interferencePower))
%       channelType       'AWGN'      'AWGN' | 'Rayleigh' | 'Rician'
%
%   opts (struct, optional):
%       .Fs          100e3    sample rate (Hz)
%       .nSamples    10000    number of I/Q samples to simulate
%       .seed        42       waveform + channel seed
%       .sps         1        samples per symbol (keep 1 to match the classifier)
%       .patternSymbols 0     0 = non-repeating random stream (realistic);
%                             32 = repeat a 32-symbol pattern, which matches the
%                             representation the Task-5 classifier was trained on
%       .name        auto     output file stem
%       .outDir      ../results
%       .timestamp   0        timestamp written into the MAT file
%
%   EXAMPLES
%       run_simulink_case();
%       run_simulink_case('BPSK', 5, 0.25, 'AWGN');
%       run_simulink_case('OFDM-QPSK', 3, 2.5, 'Rayleigh');
%
%       o.nSamples = 20000; o.seed = 7;
%       run_simulink_case('QPSK', 10, 0.5, 'Rayleigh', o);

    if nargin < 1 || isempty(modulation),        modulation = 'QPSK'; end
    if nargin < 2 || isempty(snrDb),             snrDb = 20;          end
    if nargin < 3 || isempty(interferencePower), interferencePower = 0; end
    if nargin < 4 || isempty(channelType),       channelType = 'AWGN'; end
    if nargin < 5,                               opts = struct();      end

    def = struct('Fs', 100e3, 'nSamples', 10000, 'seed', 42, 'sps', 1, ...
                 'patternSymbols', 0, 'name', '', 'outDir', '', ...
                 'timestamp', 0, 'verbose', true);
    f = fieldnames(def);
    for i = 1:numel(f)
        if ~isfield(opts, f{i}) || isempty(opts.(f{i}))
            opts.(f{i}) = def.(f{i});
        end
    end
    if ~isfield(opts, 'patternSymbols') || isempty(opts.patternSymbols)
        opts.patternSymbols = 0;
    end

    thisDir     = fileparts(mfilename('fullpath'));
    simulinkDir = fileparts(thisDir);                 % .../simulink
    if isempty(opts.outDir)
        opts.outDir = fullfile(simulinkDir, 'results');
    end
    if ~exist(opts.outDir, 'dir'); mkdir(opts.outDir); end

    modelName = 'cognitwin_sdr_phy';
    modelPath = fullfile(simulinkDir, [modelName '.slx']);

    % ------------------------------------------------------------------ model
    oldDir = pwd;
    cleanupDir = onCleanup(@() cd(oldDir));
    cd(simulinkDir);

    if ~exist(modelPath, 'file')
        error('run_simulink_case:MissingModel', ...
              ['Simulink model not found at %s.\n' ...
               'Create it first with:  cd simulink; create_cognitwin_model'], modelPath);
    end

    if ~bdIsLoaded(modelName)
        load_system(modelName);
    end

    % --------------------------------------------------- channel code mapping
    switch upper(strtrim(channelType))
        case 'AWGN',     chanCode = 0;
        case 'RAYLEIGH', chanCode = 1;
        case 'RICIAN',   chanCode = 2;
        otherwise
            error('run_simulink_case:UnknownChannel', ...
                  'channelType must be AWGN, Rayleigh or Rician (got "%s").', channelType);
    end

    % ---------------------------------------------------------- the waveform
    N  = round(opts.nSamples);
    Fs = opts.Fs;
    [tx, bitsTx, meta] = cognitwin_waveform(modulation, N, opts.seed, opts.sps, opts.patternSymbols);

    t = (0:N-1).' / Fs;
    iq_input = [t, tx];

    % =====================================================================
    % SAMPLE COUNT (Task 11, Part 15)
    % ---------------------------------------------------------------------
    % A fixed-step discrete solver executes at t = 0, Ts, 2*Ts, ..., StopTime,
    % which is  StopTime/Ts + 1  time steps. With StopTime = 0.1 and
    % Ts = 1/Fs = 1e-5 that is 10001 steps, while the input vector only covers
    % t = 0 .. (N-1)/Fs = 0.09999 s -- hence the historical 10000 in / 10001 out.
    % The extra sample was NOT a logging artefact and must not be trimmed away:
    % it was a genuine 10001st solver step whose From Workspace output came from
    % OutputAfterFinalValue (extrapolation/hold), i.e. an unphysical sample.
    %
    % The fix is at the source: stop the simulation exactly at the last input
    % sample time, so solver steps == input samples == logged samples.
    % =====================================================================
    SimStopTime = (N - 1) / Fs;

    assignin('base', 'iq_input',          iq_input);
    assignin('base', 'Fs',                Fs);
    assignin('base', 'SNR_dB',            snrDb);
    assignin('base', 'InterferencePower', interferencePower);
    assignin('base', 'ChannelCode',       chanCode);
    assignin('base', 'ChannelType',       channelType);
    assignin('base', 'ModulationType',    modulation);
    assignin('base', 'SimStopTime',       SimStopTime);

    set_param(modelName, 'Solver', 'FixedStepDiscrete', ...
                         'FixedStep', '1/Fs', ...
                         'StopTime', 'SimStopTime');

    rng(opts.seed + 1000);   % channel / noise realisation inside the model

    if opts.verbose
        fprintf('\n[Simulink] %s | SNR %.2f dB | interference %.4f | %s | N = %d | Fs = %.1f kHz\n', ...
                modulation, snrDb, interferencePower, channelType, N, Fs/1000);
    end

    tStart = tic;
    try
        simOut = sim(modelName, 'ReturnWorkspaceOutputs', 'on');
    catch
        simOut = sim(modelName);          % newer releases return SimulationOutput anyway
    end
    simSeconds = toc(tStart);

    % ------------------------------------------------------- extract outputs
    rx_struct = local_get(simOut, 'rx_iq');
    if isempty(rx_struct)
        error('run_simulink_case:NoOutput', ...
              'Model produced no rx_iq output. Check the To Workspace block.');
    end
    [rx, tOut] = local_unpack(rx_struct);

    jam_struct = local_get(simOut, 'interference_signal');
    if ~isempty(jam_struct)
        jam = local_unpack(jam_struct);
    else
        jam = [];
    end

    rx = rx(:); tOut = tOut(:);

    % Sample-count reconciliation (loud, never silent trimming).
    if numel(rx) ~= N
        warning('run_simulink_case:SampleCount', ...
                ['Logged %d samples for %d input samples. StopTime = %.9g, Ts = %.9g. ' ...
                 'Check that StopTime resolves to (N-1)/Fs.'], numel(rx), N, SimStopTime, 1/Fs);
        nUse = min(numel(rx), N);
        rx = rx(1:nUse); tOut = tOut(1:nUse);
        txUse = tx(1:nUse);
    else
        txUse = tx;
    end
    Nout = numel(rx);

    % --------------------------------------------- measurements (not models)
    % Least-squares single-tap channel estimate, then equalise before demapping.
    hHat = (tx(1:Nout)' * rx) / (tx(1:Nout)' * tx(1:Nout));
    if abs(hHat) < 1e-12; hHat = 1; end
    rxEq = rx / hHat;

    errVec        = rx - hHat * tx(1:Nout);
    measuredPower = mean(abs(rx).^2);
    errorPower    = mean(abs(errVec).^2);
    signalPower   = abs(hHat)^2 * mean(abs(tx(1:Nout)).^2);
    measuredSnrDb = 10*log10(signalPower / max(errorPower, eps));

    [ber, nErr, nBits] = cognitwin_measure_ber(modulation, rxEq, bitsTx, meta);

    if ~isempty(jam)
        measuredInterferencePower = mean(abs(jam(1:min(numel(jam), Nout))).^2);
    else
        measuredInterferencePower = NaN;
    end

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
    m.iq_samples                 = rx;                       % N x 1 complex
    m.tx_iq                      = tx(1:Nout);               % N x 1 complex reference
    m.time_vector                = tOut;                     % N x 1 seconds
    m.snr_db                     = double(snrDb);
    m.ber                        = double(ber);
    m.modulation                 = modulation;
    m.interference_power         = double(interferencePower);
    m.channel_type               = channelType;
    m.timestamp                  = double(opts.timestamp);
    m.sample_rate                = double(Fs);
    m.num_samples                = double(Nout);
    m.source                     = 'simulink';
    m.model_name                 = modelName;
    m.sim_stop_time              = double(SimStopTime);
    m.fixed_step                 = double(1/Fs);
    m.samples_per_symbol         = double(opts.sps);
    m.pattern_symbols            = double(opts.patternSymbols);
    m.seed                       = double(opts.seed);
    m.measured_power             = double(measuredPower);
    m.measured_snr_db            = double(measuredSnrDb);
    m.measured_error_power       = double(errorPower);
    m.measured_interference_power= double(measuredInterferencePower);
    m.channel_gain_real          = double(real(hHat));
    m.channel_gain_imag          = double(imag(hHat));
    m.bit_errors                 = double(nErr);
    m.bits_compared              = double(nBits);
    m.sim_wall_seconds           = double(simSeconds);

    save(outFile, '-struct', 'm', '-v7');

    if opts.verbose
        fprintf('[Simulink] logged %d samples (input %d) | measured SINR %.2f dB | BER %.6f (%d/%d bits)\n', ...
                Nout, N, measuredSnrDb, ber, nErr, nBits);
        fprintf('[Simulink] |h| = %.4f | measured jammer power %.4f | wall %.2f s\n', ...
                abs(hHat), measuredInterferencePower, simSeconds);
        fprintf('[Simulink] exported -> %s\n', outFile);
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

function [y, t] = local_unpack(s)
%LOCAL_UNPACK  Accept 'Structure With Time', 'Structure', 'Array' or timeseries.
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
