function cfg = configure_scenario(scenario_name)
    % Configures physical-layer operating parameters for specified scenario.
    % Scenario options: 'NORMAL', 'MODERATE', 'SEVERE'
    
    cfg = struct();
    cfg.scenario_name = scenario_name;
    
    switch upper(scenario_name)
        case 'NORMAL'
            cfg.snr_db = 20.0;
            cfg.interference_power = 0.0;
            cfg.channel_type = 'AWGN';
            cfg.modulation = 'QPSK';
            
        case 'MODERATE'
            cfg.snr_db = 8.0;
            cfg.interference_power = 0.40;
            cfg.channel_type = 'AWGN';
            cfg.modulation = 'QPSK';
            
        case 'SEVERE'
            cfg.snr_db = 3.0;
            cfg.interference_power = 2.50;
            cfg.channel_type = 'Rayleigh';
            cfg.modulation = 'OFDM-QPSK';
            
        otherwise
            error('Unknown scenario name: %s', scenario_name);
    end
    
    fprintf('[MATLAB PHY] Configured Scenario "%s": SNR=%.1f dB, Interference=%.2f, Channel=%s, Mod=%s\n', ...
        cfg.scenario_name, cfg.snr_db, cfg.interference_power, cfg.channel_type, cfg.modulation);
end
