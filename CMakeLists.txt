cmake_minimum_required(VERSION 3.29.3)
project(dsts_formats VERSION 0.2.0 LANGUAGES CXX)
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_BINARY_DIR)
    message(FATAL_ERROR "Use an out-of-source build: cmake -S . -B build")
endif()
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(PYBIND11_FINDPYTHON ON)
find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module)
message(STATUS "Backend Python: ${Python3_EXECUTABLE} (${Python3_VERSION})")
find_package(pybind11 CONFIG QUIET)
if(NOT pybind11_FOUND)
    execute_process(COMMAND "${Python3_EXECUTABLE}" -m pybind11 --cmakedir
        OUTPUT_VARIABLE _dsts_pybind_dir OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE _dsts_pybind_status ERROR_QUIET)
    if(_dsts_pybind_status EQUAL 0)
        find_package(pybind11 CONFIG REQUIRED PATHS "${_dsts_pybind_dir}" NO_DEFAULT_PATH)
    else()
        message(FATAL_ERROR "Install pybind11 for ${Python3_EXECUTABLE}, or pass -Dpybind11_DIR=...")
    endif()
endif()
set(SHADERS_BIN "${CMAKE_CURRENT_SOURCE_DIR}/notes/shader_params.bin")
set(SHADERS_HEADER "${CMAKE_CURRENT_BINARY_DIR}/shader_params_bin.h")
add_custom_command(OUTPUT "${SHADERS_HEADER}"
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/generate_shader_header.py"
            "${SHADERS_BIN}" "${SHADERS_HEADER}"
    DEPENDS "${SHADERS_BIN}" "${CMAKE_CURRENT_SOURCE_DIR}/generate_shader_header.py"
    COMMENT "Generating validated shader parameter definitions" VERBATIM)
pybind11_add_module(dsts_formats src/python/bindings.cpp "${SHADERS_HEADER}")
target_include_directories(dsts_formats PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
target_compile_options(dsts_formats PRIVATE $<$<CXX_COMPILER_ID:MSVC>:/EHsc>)
install(TARGETS dsts_formats LIBRARY DESTINATION . RUNTIME DESTINATION .)
option(DSTS_BUILD_REFERENCE_ADDON "Package the reference Blender adapter" OFF)
if(DSTS_BUILD_REFERENCE_ADDON)
    add_custom_target(create_archive ALL
        COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/package_addon.py"
                --addon "${CMAKE_CURRENT_SOURCE_DIR}/addon"
                --module "$<TARGET_FILE:dsts_formats>"
                --output "${CMAKE_CURRENT_BINARY_DIR}/$<CONFIG>/dsts_formats.zip"
        DEPENDS dsts_formats "${CMAKE_CURRENT_SOURCE_DIR}/tools/package_addon.py"
        COMMENT "Packaging source-only reference adapter and matching backend" VERBATIM)
endif()
