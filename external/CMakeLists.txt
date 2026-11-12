#  SPDX-License-Identifier: MIT
#
#  ES-DE
#  CMakeLists.txt (external)
#
#  CMake configuration for bundled dependencies built in-tree.
#

# This makes it possible to set options in subprojects.
set(CMAKE_POLICY_DEFAULT_CMP0077 NEW)

# Suppress warnings about cmake_minimum_required() defining deprecated versions.
set(CMAKE_WARN_DEPRECATED OFF CACHE BOOL "" FORCE)

    # Always build with optimizations enabled and without debug info.
    set(CMAKE_BUILD_TYPE Release)

unset(CMAKE_CXX_FLAGS)
unset(CMAKE_EXE_LINKER_FLAGS)

    set(BUILD_SHARED_LIBS OFF)

add_subdirectory(lunasvg EXCLUDE_FROM_ALL)

# Disable LunaSVG DLL interface warnings and narrowing conversion warnings.



# Disable threading support for rlottie as this functionality actually leads to far worse
# performance. As well there is a bug on Windows that makes rlottie hang forever on application
# shutdown if compiled using MinGW with threading support enabled.
option(LOTTIE_THREAD OFF)

option(LOTTIE_MODULE OFF)


add_subdirectory(rlottie EXCLUDE_FROM_ALL)

# rlottie generates a lot of annoying compiler warnings that we don't need to show.
    target_compile_options(rlottie PRIVATE "-w")


    add_dependencies(plutovg lunasvg)

# Build LunaSVG before rlottie.
add_dependencies(rlottie lunasvg)
