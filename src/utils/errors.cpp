#pragma once

#include <vector>
#include <string>
#include <stdexcept>
#include <cassert>

bool throwErrors = true;
std::vector<std::string> errorList{};

// Input-dependent diagnostics must never abort the host Python/Blender process.
// Mandatory bounds/index checks use direct exceptions and cannot be disabled.
#define ASSERT_OR_THROW(cond, msg) \
    do { \
        if (!(cond)) { \
            if (throwErrors) throw std::runtime_error(msg); \
            else errorList.push_back(msg); \
        } \
    } while(0)
