#pragma once

#include <cstdint>
#include <cstring>
#include <istream>
#include <limits>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

namespace dsts {
inline uint64_t checkedAdd(uint64_t a, uint64_t b, const char* what) {
    if (b > std::numeric_limits<uint64_t>::max() - a)
        throw std::runtime_error(std::string(what) + ": offset overflow");
    return a + b;
}

// Bounds are checked before allocating or seeking. These checks are mandatory,
// including when the optional semantic diagnostics are set to collect errors.
class CheckedBinary {
    std::istream& stream;
    uint64_t origin;
    uint64_t length;
public:
    CheckedBinary(std::istream& input, uint64_t base = 0) : stream(input), origin(base) {
        stream.clear();
        stream.seekg(0, std::ios::end);
        const auto end = stream.tellg();
        if (end < 0 || base > static_cast<uint64_t>(end))
            throw std::runtime_error("Binary base is outside the input");
        length = static_cast<uint64_t>(end) - base;
    }
    uint64_t size() const { return length; }
    void range(uint64_t offset, uint64_t count, uint64_t width, const char* what) const {
        if (offset > length || (width && count > (length - offset) / width))
            throw std::runtime_error(std::string(what) + ": range exceeds input");
    }
    void bytes(uint64_t offset, void* output, uint64_t count, const char* what) {
        range(offset, count, 1, what);
        if (count > static_cast<uint64_t>(std::numeric_limits<std::streamsize>::max()))
            throw std::runtime_error(std::string(what) + ": read is too large");
        stream.clear();
        stream.seekg(static_cast<std::streamoff>(origin + offset));
        if (count) stream.read(static_cast<char*>(output), static_cast<std::streamsize>(count));
        if (!stream) throw std::runtime_error(std::string(what) + ": truncated read");
    }
    template<class T> T object(uint64_t offset, const char* what) {
        static_assert(std::is_trivially_copyable_v<T>);
        T result{}; bytes(offset, &result, sizeof(T), what); return result;
    }
    template<class T> std::vector<T> array(uint64_t offset, uint64_t count, const char* what) {
        range(offset, count, sizeof(T), what);
        if (count > std::vector<T>().max_size()) throw std::runtime_error(std::string(what) + ": count is too large");
        std::vector<T> result(static_cast<size_t>(count));
        bytes(offset, result.data(), count * sizeof(T), what); return result;
    }
    std::string string(uint64_t offset, const char* what) {
        range(offset, 1, 1, what);
        stream.clear(); stream.seekg(static_cast<std::streamoff>(origin + offset));
        std::string value;
        for (uint64_t i = offset; i < length; ++i) {
            char c;
            if (!stream.get(c)) break;
            if (!c) return value;
            value.push_back(c);
        }
        throw std::runtime_error(std::string(what) + ": unterminated string");
    }
};
}
