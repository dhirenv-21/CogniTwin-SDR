function b = cognitwin_gray2bin(g)
%COGNITWIN_GRAY2BIN  Gray code integer -> binary integer.
%   Bit-exact match of gray_to_binary() in src/modulation/digital/common.py.
    b = g;
    mask = bitshift(g, -1);
    while mask ~= 0
        b = bitxor(b, mask);
        mask = bitshift(mask, -1);
    end
end
