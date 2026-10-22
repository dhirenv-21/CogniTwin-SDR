function export_results(filepath, iq_samples, snr_db, ber, modulation, interference_power, channel_type, timestamp)
    % Exports physical-layer simulation measurements to a MAT file for Python ingestion.
    
    % Ensure complex double formatting for float precision
    iq_samples = double(iq_samples);
    snr_db = double(snr_db);
    ber = double(ber);
    interference_power = double(interference_power);
    timestamp = double(timestamp);
    
    save(filepath, 'iq_samples', 'snr_db', 'ber', 'modulation', 'interference_power', 'channel_type', 'timestamp', '-v7');
    fprintf('[MATLAB PHY Export] Saved physical-layer measurement to "%s"\n', filepath);
end
