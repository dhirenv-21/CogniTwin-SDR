function g = cognitwin_bin2gray(b)
%COGNITWIN_BIN2GRAY  Binary integer -> Gray code integer.
%   Bit-exact match of binary_to_gray() in src/modulation/digital/common.py.
    g = bitxor(b, bitshift(b, -1));
end
