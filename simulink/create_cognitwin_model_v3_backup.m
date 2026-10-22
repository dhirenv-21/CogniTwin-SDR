%% CREATE_COGNITWIN_MODEL   (v3 - PHY debug/validation rebuild)
% Cognitwin-SDR Physical Layer
%
%   iq_input_i (From Workspace, REAL)  --\
%   iq_input_q (From Workspace, REAL)  --/--> PHY_Channel
%   SNR_dB            (Constant)       ----->    x   = complex(xi, xq)
%   InterferencePower (Constant)       ----->    h   = complex(h_re, h_im)
%   ChannelGainRe     (Constant)       ----->    n   = sqrt(10^(-SNR/10)/2)*(randn+j*randn)
%   ChannelGainIm     (Constant)       ----->    jam = sqrt(P/2)*(randn+j*randn)
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
%
% USAGE
%   cd simulink
%   create_cognitwin_model
%   cd matlab
%   diagnose_simulink_phy          % node-by-node health check, run this first
%   run_simulink_case('QPSK', 10, 0, 'AWGN')

clear modelName

modelName = 'cognitwin_sdr_phy';

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
SimStopTime       = (10000 - 1) / Fs;

assignin('base','Fs',Fs);
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

if exist([modelName '.slx'],'file')
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

%% ============================================================
% MATLAB CHANNEL FUNCTION
% =============================================================

add_block('simulink/User-Defined Functions/MATLAB Function',...
    [modelName '/PHY_Channel'],...
    'Position',[380 100 660 450]);

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
    'function [y, jam, noise, x] = fcn(xi, xq, snr_db, interf_power, h_re, h_im)', ...
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

phyScript = sprintf('%s\n', phyLines{:});

% Fail loudly rather than installing an empty or truncated function body.
if isempty(strfind(phyScript, 'y = h*x + jam + noise;')) || ...
        isempty(strfind(phyScript, 'function [y, jam, noise, x] = fcn('))
    error('create_cognitwin_model:BadPhyScript', ...
          'Generated PHY_Channel script is missing its signature or output equation.');
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

add_line(modelName,'PHY_Channel/1','RX_IQ_TO_WORKSPACE/1','autorouting','on');
add_line(modelName,'PHY_Channel/1','IQ_SCOPE/1','autorouting','on');
add_line(modelName,'PHY_Channel/2','INTERFERENCE_TO_WORKSPACE/1','autorouting','on');
add_line(modelName,'PHY_Channel/3','NOISE_TO_WORKSPACE/1','autorouting','on');
add_line(modelName,'PHY_Channel/4','TX_ECHO_TO_WORKSPACE/1','autorouting','on');

%% ============================================================
% SAVE
% =============================================================

save_system(modelName);

fprintf('\n');
fprintf('=================================================================\n');
fprintf(' Cognitwin-SDR Simulink model created (v3 - PHY validated build)\n');
fprintf('=================================================================\n');
fprintf('Model        : %s.slx\n',modelName);
fprintf('Sample rate  : %.1f kHz\n',Fs/1000);
fprintf('Inputs       : iq_input_i, iq_input_q   (REAL [t, data] matrices)\n');
fprintf('Outputs      : rx_iq, interference_signal, noise_signal, tx_echo\n');
fprintf('Channel gain : supplied by the driver as ChannelGainRe/Im\n');
fprintf('StopTime     : SimStopTime = %.9g s  -> %d solver steps\n', ...
        SimStopTime, round(SimStopTime*Fs)+1);
fprintf('=================================================================\n');
fprintf('Next:  cd matlab;  diagnose_simulink_phy      %% verify the PHY first\n');
fprintf('       then:       run_simulink_case(''QPSK'', 10, 0, ''AWGN'')\n');
