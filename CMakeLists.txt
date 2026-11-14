cmake_minimum_required(VERSION 3.29.3)

# Set project name and language
project(dsts_formats LANGUAGES CXX)

# Specify the C++ standard
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Explicitly find Python before pybind11 so the correct version is locked in.
# Override on the command line: cmake -DPython3_ROOT_DIR=/path/to/python313
if(NOT Python3_ROOT_DIR AND NOT Python3_EXECUTABLE)
    message(STATUS "No Python3 hint provided; cmake will pick the system default.")
endif()
find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module)
message(STATUS "Using Python: ${Python3_EXECUTABLE} (${Python3_VERSION})")

find_package(pybind11 REQUIRED)

set(SHADERS_BIN    ${CMAKE_CURRENT_SOURCE_DIR}/notes/shader_params.bin)
set(SHADERS_HEADER ${CMAKE_CURRENT_BINARY_DIR}/shader_params_bin.h)

# Use Python (found by pybind11) to generate the header — works on Windows
# without requiring xxd/sed Unix tools.
add_custom_command(
    OUTPUT ${SHADERS_HEADER}
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/generate_shader_header.py
            ${SHADERS_BIN}
            ${SHADERS_HEADER}
    DEPENDS ${SHADERS_BIN}
    COMMENT "Converting shader_params.bin to constexpr C++ header"
    VERBATIM
)

add_custom_target(generate_shaders_header ALL DEPENDS ${SHADERS_HEADER})

pybind11_add_module(dsts_formats src/python/bindings.cpp)
add_dependencies(dsts_formats generate_shaders_header)
target_include_directories(dsts_formats PRIVATE ${CMAKE_CURRENT_BINARY_DIR})

# Define staging folder
set(PACKAGE_DIR "${CMAKE_CURRENT_BINARY_DIR}/package")

add_custom_target(create_archive ALL
    # Step 1: create staging folder
    COMMAND ${CMAKE_COMMAND} -E remove_directory "${PACKAGE_DIR}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${PACKAGE_DIR}"

    # Step 2: copy the entire addon folder contents into staging
    COMMAND ${CMAKE_COMMAND} -E copy_directory
        "${CMAKE_CURRENT_SOURCE_DIR}/addon"
        "${PACKAGE_DIR}/${CMAKE_PROJECT_NAME}"

    # Step 3: copy the built pybind11 module into the same staging folder
    COMMAND ${CMAKE_COMMAND} -E copy
        "$<TARGET_FILE:dsts_formats>"
        "${PACKAGE_DIR}/${CMAKE_PROJECT_NAME}/$<TARGET_FILE_NAME:dsts_formats>"

    # Step 4: create zip archive from staging folder
    COMMAND ${CMAKE_COMMAND} -E chdir "${PACKAGE_DIR}"
        ${CMAKE_COMMAND} -E tar "cf"
        "${CMAKE_CURRENT_BINARY_DIR}/$<CONFIG>/${CMAKE_PROJECT_NAME}.zip"
        "${PACKAGE_DIR}/${CMAKE_PROJECT_NAME}/"
        --format=zip

    DEPENDS dsts_formats
)