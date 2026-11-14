#pragma once

#include <streambuf>
#include <vector>
#include <ostream>
#include <algorithm>
#include <cstring>
#include <cstdint>

class MemoryBuffer : public std::streambuf {
public:
    MemoryBuffer() {
        // No preallocation, starts empty
        setp(nullptr, nullptr);
    }

    std::vector<char> &data() { return buffer_; }
    const std::vector<char> &data() const { return buffer_; }

protected:
    int_type overflow(int_type ch) override {
        if(traits_type::eq_int_type(ch,traits_type::eof())) return traits_type::not_eof(ch);
        const char value=traits_type::to_char_type(ch);
        return xsputn(&value,1)==1 ? ch : traits_type::eof();
    }

    std::streamsize xsputn(const char* source,std::streamsize count) override {
        if(count<0 || static_cast<uint64_t>(count)>buffer_.max_size()-position_) return 0;
        const size_t end=position_+static_cast<size_t>(count);
        if(end>buffer_.size()) buffer_.resize(end,0);
        if(count) std::memcpy(buffer_.data()+position_,source,static_cast<size_t>(count));
        position_=end;
        return count;
    }

    pos_type seekoff(off_type offset,std::ios_base::seekdir direction,std::ios_base::openmode which) override {
        if(!(which & std::ios_base::out)) return pos_type(off_type(-1));
        size_t start=0;
        if(direction==std::ios_base::cur) start=position_;
        else if(direction==std::ios_base::end) start=buffer_.size();
        else if(direction!=std::ios_base::beg) return pos_type(off_type(-1));
        if(offset<0 && static_cast<uint64_t>(-(offset+1))+1>start) return pos_type(off_type(-1));
        if(offset>=0 && static_cast<uint64_t>(offset)>buffer_.max_size()-start) return pos_type(off_type(-1));
        const size_t next=offset<0 ? start-static_cast<size_t>(-(offset+1))-1 : start+static_cast<size_t>(offset);
        if(next>buffer_.size()) buffer_.resize(next,0);
        position_=next;
        return pos_type(static_cast<off_type>(next));
    }

    pos_type seekpos(pos_type pos,std::ios_base::openmode which) override {
        return seekoff(static_cast<off_type>(pos),std::ios_base::beg,which);
    }

private:
    std::vector<char> buffer_;
    size_t position_=0;

};

class MemoryStream : public std::ostream {
public:
    MemoryStream() : std::ostream(&buffer_) {}
    std::vector<char> &data() { return buffer_.data(); }
    const std::vector<char> &data() const { return buffer_.data(); }
    std::string str() const { return std::string(buffer_.data().begin(), buffer_.data().end()); }
private:
    MemoryBuffer buffer_;
};