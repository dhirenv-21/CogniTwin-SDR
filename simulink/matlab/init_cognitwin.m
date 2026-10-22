% CogniTwin-SDR: MATLAB/Simulink Physical Layer Initialization
% Initializes SDR simulation parameters, sampling rate, and subcarrier setup.

fs = 100000.0;          % Sample rate: 100 kHz
n_fft = 64;             % OFDM subcarriers
cp_len = 16;            % Cyclic prefix length
symbol_length = 512;    % Window size for analysis

fprintf('[MATLAB/Simulink PHY] Initialized SDR Parameters: Fs=%.1f kHz, N_fft=%d, CP=%d\n', fs/1000, n_fft, cp_len);
