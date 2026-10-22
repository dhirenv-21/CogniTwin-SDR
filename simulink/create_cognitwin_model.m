%% CREATE_COGNITWIN_MODEL   (v4 - seeded PHY noise; v3 signal path unchanged)
% Cognitwin-SDR Physical Layer
%
%   iq_input_i (From Workspace, REAL)  --\
%   iq_input_q (From Workspace, REAL)  --/--> PHY_Channel
%   SNR_dB            (Constant)       ----->    x   = complex(xi, xq)
%   InterferencePower (Constant)       ----->    h   = complex(h_re, h_im)
%   ChannelGainRe     (Constant)       ----->    n   = sqrt(10^(-SNR/10)/2)*(randn+j*randn)
%   ChannelGainIm     (Constant)       ----->    jam = sqrt(P/2)*(randn+j*randn)
%   NOISE_I/Q, JAM_I/Q (Random Number) ----->    (default noise source, see below)
%                                                y   = h*x + jam + n
%        +--> rx_iq                (To Workspace)  the received waveform
%        +--> interference_signal  (To Workspace)  the jammer, on its own
%        +--> noise_signal         (To Workspace)  the AWGN, on its own
%        +--> tx_echo              (To Workspace)  x as PHY_Channel actually saw it
%        +--> IQ_SCOPE
%
% =====================================================================
% WHY v3 EXISTS - ROOT CAUSE OF THE BROKEN PHY RESULTS
% =====================================================================
% v2 fed the model with
%
%       iq_input = [t, tx];        % tx complex  ->  ENTIRE MATRIX complex
%
% The From Workspace block's array format requires a REAL matrix whose first
% column is a real, monotonically increasing time vector. Because tx is complex,
% column 1 (time) became complex as well, the block could not resolve any time
% sample, and INPUT_IQ emitted 0 for the whole simulation.
%
% The wanted signal therefore never reached PHY_Channel. Everything downstream
% was measuring pure noise:
%
%   * BER ~ 0.4977              -> a coin flip, i.e. no signal
%   * |h_LS| ~ 0.0037-0.0083    -> exactly sqrt(P_rx / N): the least-squares fit
%                                  of a transmit reference to noise it is not in
%   * measured SINR ~ -48 dB    -> |h_LS|^2 / P_rx, the same artefact in dB
%   * jammer power ~ 0.2462     -> CORRECT, because the jammer is generated
%                                  independently and never depended on x
%
% v3 removes the failure mode entirely rather than patching around it:
%
%   1. I and Q enter as TWO SEPARATE REAL From Workspace signals. No complex
%      array is ever handed to a From Workspace block, so the time column can
%      never be corrupted.
%   2. PHY_Channel echoes the reconstructed x back out (tx_echo). run_simulink_case
%      compares it against the intended tx and ABORTS with a precise message if
%      the input path is dead. A silent zero-signal run is now impossible.
%   3. The noise and the jammer are logged as separate signals, so signal, noise
%      and interference powers are MEASURED from real arrays instead of being
%      inferred from a least-squares fit.
%   4. The channel gain h is supplied by the driver as two real constants, so it
%      is exactly known, exactly reproducible, and exported with the results.
%      No persistent state inside the MATLAB Function block.
%
% =====================================================================
% WHY v4 EXISTS - THE NOISE WAS NEVER SEEDED
% =====================================================================
% randn inside a MATLAB Function block draws from the block's OWN generator,
% not from MATLAB's global stream, and that generator restarts from the same
% state at the beginning of every simulation. The driver's rng(seed) call
% therefore never reached the model. Measured on the v3 exports in
% simulink/results/baseline/:
%
%   * noise_iq is bit-identical for seeds 11, 23 and 37 (max difference 0.0)
%   * noise_iq at 0 dB is exactly 10x noise_iq at 20 dB (same draw, rescaled)
%   * interference_iq at P = 4 is exactly 2x the P = 1 draw
%
% Every run used ONE noise realisation, so "multi-seed" repeatability only
% varied the bits and h, never the noise.
%
% NOISE SOURCE (set the variable NoiseSource before running this script):
%
%   'random_number_blocks'  (DEFAULT) four Simulink Random Number blocks,
%       NOISE_I, NOISE_Q, JAM_I, JAM_Q: zero mean, unit variance, sample time
%       1/Fs, each with its own Seed = mod(4*NoiseSeed + k, 4294967291).
%       The Seed parameter is the documented control of each block's own
%       generator, so the seed demonstrably reaches the noise source.
%       PHY_Channel scales them: noise = sqrt(P_n/2)*complex(ni, nq).
%
%   'block_rng'  randn inside PHY_Channel, seeded once per simulation by
%       rng(noise_seed) behind a persistent guard (NOISE_SEED constant).
%       Depends on rng being supported in a MATLAB Function block; use only
%       if D13 passes with it.
%
%   Example:   NoiseSource = 'block_rng';  create_cognitwin_model
%
% Either way the driver sets NoiseSeed = opts.seed + 1000, and D13 in
% diagnose_simulink_phy measures whether the seed really controls the noise.
% The y = h*x + jam + n equation is unchanged.
%
% Channel model (unchanged from the project specification):
%       AWGN      h = 1
%       Rayleigh  h ~ CN(0,1), E|h|^2 = 1, one draw per run (block fading)
%       Rician    h = (sqrt(K) + CN(0,1))/sqrt(K+1), K = 2, E|h|^2 = 1
%
% Sample count (unchanged from v2): StopTime = SimStopTime = (N-1)/Fs, so the
% fixed-step solver takes exactly N steps for N input samples.
%
% Previous generators are preserved verbatim as
%   create_cognitwin_model_v1_backup.m   (original)
%   create_cognitwin_model_v2_backup.m   (complex From Workspace version)
%   create_cognitwin_model_v3_backup.m   (real I/Q inputs, unseeded noise)
%
% USAGE
%   cd simulink
%   create_cognitwin_model
%   cd matlab
%   diagnose_simulink_phy          % node-by-node health check, run this first
%   run_simulink_case('QPSK', 10, 0, 'AWGN')

clear modelName

modelName = 'cognitwin_sdr_phy';

% Build, back up and save next to this script, whatever the current folder.
% run_simulink_case and diagnose_simulink_phy load the model from here.
generatorDir = fileparts(mfilename('fullpath'));
if ~isempty(generatorDir) && ~strcmp(pwd, generatorDir)
    fprintf('Changing folder to %s (model is saved next to this script)\n', generatorDir);
    cd(generatorDir);
end

if ~exist('NoiseSource','var') || isempty(NoiseSource)
    NoiseSource = 'random_number_blocks';
end
NoiseSource = lower(strtrim(char(NoiseSource)));
if ~any(strcmp(NoiseSource, {'random_number_blocks','block_rng'}))
    error('create_cognitwin_model:BadNoiseSource', ...
          'NoiseSource must be ''random_number_blocks'' or ''block_rng'' (got ''%s'').', NoiseSource);
end

%% ============================================================
% PARAMETERS
% =============================================================

Fs                = 100e3;
SNR_dB            = 20;
InterferencePower = 0;
ChannelType       = 'AWGN';
ChannelGainRe     = 1;
ChannelGainIm     = 0;
ModulationType    = 'QPSK';
NoiseSeed         = 1;
SimStopTime       = (10000 - 1) / Fs;

assignin('base','Fs',Fs);
assignin('base','NoiseSeed',NoiseSeed);
assignin('base','SNR_dB',SNR_dB);
assignin('base','InterferencePower',InterferencePower);
assignin('base','ChannelType',ChannelType);
assignin('base','ChannelGainRe',ChannelGainRe);
assignin('base','ChannelGainIm',ChannelGainIm);
assignin('base','ModulationType',ModulationType);
assignin('base','SimStopTime',SimStopTime);

% Default REAL inputs so the freshly created model is immediately runnable.
t0 = (0:9999).'/Fs;
assignin('base','iq_input_i',[t0, cos(2*pi*1000*t0)]);
assignin('base','iq_input_q',[t0, sin(2*pi*1000*t0)]);

%% ============================================================
% RESULTS DIRECTORY
% =============================================================

projectRoot = pwd;
resultsDir  = fullfile(projectRoot,'results');

if ~exist(resultsDir,'dir')
    mkdir(resultsDir);
end

%% ============================================================
% CLOSE / BACK UP OLD MODEL
% =============================================================

if bdIsLoaded(modelName)
    close_system(modelName,0);
end

if exist(fullfile(pwd, [modelName '.slx']),'file') == 4 || exist(fullfile(pwd, [modelName '.slx']),'file') == 2
    backupName = sprintf('%s_backup_%s.slx', modelName, datestr(now,'yyyymmdd_HHMMSS'));
    copyfile([modelName '.slx'], backupName);
    fprintf('Existing model backed up to %s\n', backupName);
    delete([modelName '.slx']);
end

%% ============================================================
% CREATE MODEL
% =============================================================

new_system(modelName);
open_system(modelName);

set_param(modelName,...
    'Solver','FixedStepDiscrete',...
    'FixedStep','1/Fs',...
    'StopTime','SimStopTime');

%% ============================================================
% INPUTS - TWO REAL STREAMS (never complex)
% =============================================================
%
%   iq_input_i = [t, real(tx)]      REAL N x 2
%   iq_input_q = [t, imag(tx)]      REAL N x 2
%
% They are recombined into a complex baseband signal inside PHY_Channel.

add_block('simulink/Sources/From Workspace',...
    [modelName '/INPUT_I'],...
    'VariableName','iq_input_i',...
    'Interpolate','off',...
    'OutputAfterFinalValue','Holding final value',...
    'Position',[40 100 200 140]);

add_block('simulink/Sources/From Workspace',...
    [modelName '/INPUT_Q'],...
    'VariableName','iq_input_q',...
    'Interpolate','off',...
    'OutputAfterFinalValue','Holding final value',...
    'Position',[40 170 200 210]);

%% ============================================================
% PARAMETER CONSTANTS
% =============================================================

add_block('simulink/Sources/Constant',...
    [modelName '/SNR_PARAMETER'],...
    'Value','SNR_dB',...
    'Position',[40 250 200 285]);

add_block('simulink/Sources/Constant',...
    [modelName '/INTERFERENCE_PARAMETER'],...
    'Value','InterferencePower',...
    'Position',[40 305 200 340]);

add_block('simulink/Sources/Constant',...
    [modelName '/CHANNEL_GAIN_RE'],...
    'Value','ChannelGainRe',...
    'Position',[40 360 200 395]);

add_block('simulink/Sources/Constant',...
    [modelName '/CHANNEL_GAIN_IM'],...
    'Value','ChannelGainIm',...
    'Position',[40 415 200 450]);

if strcmp(NoiseSource, 'block_rng')
    add_block('simulink/Sources/Constant',...
        [modelName '/NOISE_SEED'],...
        'Value','NoiseSeed',...
        'Position',[40 470 200 505]);
else
    % One independent unit-variance Gaussian stream per quadrature. Seeds are
    % spread by 4*NoiseSeed so consecutive run seeds never share a stream.
    rnNames = {'NOISE_I','NOISE_Q','JAM_I','JAM_Q'};
    for k = 1:numel(rnNames)
        add_block('simulink/Sources/Random Number',...
            [modelName '/' rnNames{k}],...
            'Mean','0',...
            'Variance','1',...
            'Seed',sprintf('mod(4*NoiseSeed + %d, 4294967291)', k-1),...
            'SampleTime','1/Fs',...
            'Position',[40 470+55*(k-1) 200 505+55*(k-1)]);
    end
end

%% ============================================================
% MATLAB CHANNEL FUNCTION
% =============================================================

add_block('simulink/User-Defined Functions/MATLAB Function',...
    [modelName '/PHY_Channel'],...
    'Position',[380 100 660 680]);

%% ============================================================
% OUTPUTS
% =============================================================

add_block('simulink/Sinks/To Workspace',...
    [modelName '/RX_IQ_TO_WORKSPACE'],...
    'VariableName','rx_iq',...
    'SaveFormat','Structure With Time',...
    'MaxDataPoints','inf','Decimation','1',...
    'Position',[820 100 1000 140]);

add_block('simulink/Sinks/To Workspace',...
    [modelName '/INTERFERENCE_TO_WORKSPACE'],...
    'VariableName','interference_signal',...
    'SaveFormat','Structure With Time',...
    'MaxDataPoints','inf','Decimation','1',...
    'Position',[820 180 1000 220]);

add_block('simulink/Sinks/To Workspace',...
    [modelName '/NOISE_TO_WORKSPACE'],...
    'VariableName','noise_signal',...
    'SaveFormat','Structure With Time',...
    'MaxDataPoints','inf','Decimation','1',...
    'Position',[820 260 1000 300]);

add_block('simulink/Sinks/To Workspace',...
    [modelName '/TX_ECHO_TO_WORKSPACE'],...
    'VariableName','tx_echo',...
    'SaveFormat','Structure With Time',...
    'MaxDataPoints','inf','Decimation','1',...
    'Position',[820 340 1000 380]);

add_block('simulink/Sinks/Scope',...
    [modelName '/IQ_SCOPE'],...
    'Position',[820 420 1000 480]);

%% ============================================================
% MATLAB FUNCTION SCRIPT
% =============================================================

rt = sfroot;

chart = find(rt,...
    '-isa','Stateflow.EMChart',...
    'Path',[modelName '/PHY_Channel']);

if isempty(chart)
    error('Could not locate PHY_Channel MATLAB Function block.');
end

% ------------------------------------------------------------------------
% NOTE ON HOW THIS SCRIPT IS BUILT
% ------------------------------------------------------------------------
% This used to be a bracket concatenation of the form
%
%     chart.Script = [ 'line one'   newline ...
%                      'line two'   newline ... ];
%
% Inside [ ], WHITESPACE is the element delimiter. When a line grew long
% enough that the padding before "newline" disappeared, the source became
%
%     '...power.'newline ...
%
% i.e. a closing quote immediately followed by an identifier with no
% delimiter between them. MATLAB cannot separate the two tokens and reports
%
%     Invalid expression.   (line 257, column 80)
%
% A cell array with EXPLICIT COMMAS has no whitespace sensitivity at all, so
% the failure mode cannot recur no matter how the lines are formatted or
% re-indented later. sprintf('%s\n', ...) then joins them.
%
% The generated PHY script text is byte-for-byte identical to the intended
% original. No equation, coefficient or signal-path line is changed.
% ------------------------------------------------------------------------

phyLines = { ...
    'function [y, jam, noise, x] = fcn(xi, xq, snr_db, interf_power, h_re, h_im, noise_seed)', ...
    '%#codegen', ...
    '% CogniTwin-SDR PHY channel:  y = h*x + jam + noise', ...
    '%', ...
    '%   xi, xq       : REAL in-phase / quadrature samples of the wanted signal.', ...
    '%                  Kept real all the way from the workspace so that the', ...
    '%                  From Workspace time column can never become complex.', ...
    '%   h_re, h_im   : channel gain supplied by the driver (AWGN -> 1 + 0i).', ...
    '%   noise        : complex AWGN, power = 10^(-snr_db/10)', ...
    '%   jam          : INDEPENDENT complex Gaussian jammer, power = interf_power.', ...
    '%                  It is generated from its own randn draws and never from x,', ...
    '%                  so it can never be a coherent copy of the wanted signal.', ...
    '%', ...
    '% x is echoed back out so the driver can prove the wanted signal actually', ...
    '% arrived at this block.', ...
    '%', ...
    '%   noise_seed   : seeds the randn generator of THIS block once, on the first', ...
    '%                  step of each simulation. Without it the block restarts from', ...
    '%                  the same generator state every run, so every run gets the', ...
    '%                  same noise and jammer realisation.', ...
    '', ...
    'persistent rngSeeded', ...
    'if isempty(rngSeeded)', ...
    '    rng(noise_seed);', ...
    '    rngSeeded = true;', ...
    'end', ...
    '', ...
    'x = complex(xi, xq);', ...
    'h = complex(h_re, h_im);', ...
    '', ...
    'noisePower = 10^(-snr_db/10);', ...
    'noise = sqrt(noisePower/2) * complex(randn, randn);', ...
    'jam   = sqrt(max(interf_power,0)/2) * complex(randn, randn);', ...
    '', ...
    'y = h*x + jam + noise;', ...
    'end' ...
};

if strcmp(NoiseSource, 'random_number_blocks')
    % Same channel; the four Gaussian streams come from the seeded Random
    % Number blocks instead of randn inside this block.
    phyLines = { ...
        'function [y, jam, noise, x] = fcn(xi, xq, snr_db, interf_power, h_re, h_im, ni, nq, ji, jq)', ...
        '%#codegen', ...
        '% CogniTwin-SDR PHY channel:  y = h*x + jam + noise', ...
        '%', ...
        '%   xi, xq       : REAL in-phase / quadrature samples of the wanted signal.', ...
        '%   h_re, h_im   : channel gain supplied by the driver (AWGN -> 1 + 0i).', ...
        '%   ni, nq       : unit-variance Gaussian streams from the NOISE_I / NOISE_Q', ...
        '%                  Random Number blocks (seeded from NoiseSeed).', ...
        '%   ji, jq       : the same from JAM_I / JAM_Q, independent of the noise', ...
        '%                  and never derived from x.', ...
        '%   noise        : complex AWGN, power = 10^(-snr_db/10)', ...
        '%   jam          : complex Gaussian jammer, power = interf_power', ...
        '', ...
        'x = complex(xi, xq);', ...
        'h = complex(h_re, h_im);', ...
        '', ...
        'noisePower = 10^(-snr_db/10);', ...
        'noise = sqrt(noisePower/2) * complex(ni, nq);', ...
        'jam   = sqrt(max(interf_power,0)/2) * complex(ji, jq);', ...
        '', ...
        'y = h*x + jam + noise;', ...
        'end' ...
    };
    seedMarker = 'complex(ni, nq);';
else
    seedMarker = 'rng(noise_seed);';
end

phyScript = sprintf('%s\n', phyLines{:});

% Fail loudly rather than installing an empty or truncated function body.
if isempty(strfind(phyScript, 'y = h*x + jam + noise;')) || ...
        isempty(strfind(phyScript, 'function [y, jam, noise, x] = fcn(')) || ...
        isempty(strfind(phyScript, seedMarker))
    error('create_cognitwin_model:BadPhyScript', ...
          'Generated PHY_Channel script is missing its signature, output equation or noise seeding.');
end

chart.Script = phyScript;

%% ============================================================
% CONNECTIONS
% =============================================================

add_line(modelName,'INPUT_I/1','PHY_Channel/1','autorouting','on');
add_line(modelName,'INPUT_Q/1','PHY_Channel/2','autorouting','on');
add_line(modelName,'SNR_PARAMETER/1','PHY_Channel/3','autorouting','on');
add_line(modelName,'INTERFERENCE_PARAMETER/1','PHY_Channel/4','autorouting','on');
add_line(modelName,'CHANNEL_GAIN_RE/1','PHY_Channel/5','autorouting','on');
add_line(modelName,'CHANNEL_GAIN_IM/1','PHY_Channel/6','autorouting','on');
if strcmp(NoiseSource, 'block_rng')
    add_line(modelName,'NOISE_SEED/1','PHY_Channel/7','autorouting','on');
else
    for k = 1:numel(rnNames)
        add_line(modelName,[rnNames{k} '/1'],sprintf('PHY_Channel/%d', 6+k),'autorouting','on');
    end
end

add_line(modelName,'PHY_Channel/1','RX_IQ_TO_WORKSPACE/1','autorouting','on');
add_line(modelName,'PHY_Channel/1','IQ_SCOPE/1','autorouting','on');
add_line(modelName,'PHY_Channel/2','INTERFERENCE_TO_WORKSPACE/1','autorouting','on');
add_line(modelName,'PHY_Channel/3','NOISE_TO_WORKSPACE/1','autorouting','on');
add_line(modelName,'PHY_Channel/4','TX_ECHO_TO_WORKSPACE/1','autorouting','on');

%% ============================================================
% SAVE
% =============================================================

% Compile once before saving so a broken PHY_Channel (e.g. an unsupported
% function inside the MATLAB Function block) fails HERE, with its own message.
try
    set_param(modelName,'SimulationCommand','update');
catch errUpdate
    error('create_cognitwin_model:UpdateFailed', ...
          ['Model update/compile failed (NoiseSource = %s):\n%s\n' ...
           'The model was NOT saved.'], NoiseSource, errUpdate.message);
end

save_system(modelName);

fprintf('\n');
fprintf('=================================================================\n');
fprintf(' Cognitwin-SDR Simulink model created (v4 - seeded PHY noise)\n');
fprintf('=================================================================\n');
fprintf('Model        : %s.slx\n',modelName);
fprintf('Sample rate  : %.1f kHz\n',Fs/1000);
fprintf('Inputs       : iq_input_i, iq_input_q   (REAL [t, data] matrices)\n');
fprintf('Outputs      : rx_iq, interference_signal, noise_signal, tx_echo\n');
fprintf('Channel gain : supplied by the driver as ChannelGainRe/Im\n');
fprintf('Noise source : %s, seeded from NoiseSeed (set by the driver)\n', NoiseSource);
fprintf('StopTime     : SimStopTime = %.9g s  -> %d solver steps\n', ...
        SimStopTime, round(SimStopTime*Fs)+1);
fprintf('=================================================================\n');
fprintf('Next:  cd matlab;  diagnose_simulink_phy      %% verify the PHY first\n');
fprintf('       then:       run_simulink_case(''QPSK'', 10, 0, ''AWGN'')\n');
