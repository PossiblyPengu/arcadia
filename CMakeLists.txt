#  SPDX-License-Identifier: MIT
#
#  Arcadia
#  CMakeLists.txt
#
#  Main CMake configuration file.
#  Sets up the overall build environment including dependencies detection, build options,
#  compiler and linker flags and preprocessor directives.
#

cmake_minimum_required(VERSION 3.13)

project(arcadia)

# Application version, update this when making a new release.
set(ES_VERSION 3.4.1)

# Arcadia's own version: the VERSION file. Bumping it and pushing to main publishes a release (see the workflow).
file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION" ARCADIA_VERSION LIMIT_COUNT 1)
add_compile_definitions(ARCADIA_VERSION="${ARCADIA_VERSION}")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION")

# Set this to ON to show verbose compiler output (e.g. compiler flags, include directories etc.)
set(CMAKE_VERBOSE_MAKEFILE OFF CACHE BOOL "Show verbose compiler output" FORCE)

# Package type to use for CPack on Linux.
set(LINUX_CPACK_GENERATOR DEB CACHE STRING "CPack generator, DEB or RPM")

# Add local find modules to the CMake path.
list(APPEND CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/CMake/Utils
                              ${CMAKE_CURRENT_SOURCE_DIR}/CMake/Packages)

# Define the options.
option(GL "Set to ON if targeting Desktop OpenGL" ON)
option(GLES "Set to ON if targeting OpenGL ES" OFF)
option(APPLICATION_UPDATER "Set to ON to build with the upstream ES-DE application updater (off in this fork, which updates itself from its own releases, see deck/)" OFF)
option(COMPILE_LOCALIZATIONS "Set to OFF to skip compilation of localization message catalogs" ON)
option(APPIMAGE_BUILD "Set to ON when building as an AppImage" OFF)
option(AUR_BUILD "Set to ON when building for the AUR" OFF)
option(FLATPAK_BUILD "Set to ON when building as a Flatpak" OFF)
option(STEAM_DECK "Set to ON to enable a Valve Steam Deck specific build" OFF)
option(RETRODECK "Set to ON to enable a RetroDECK specific build" OFF)
option(BUNDLED_CERTS "Set to ON to use bundled TLS/SSL certificates" OFF)
option(VIDEO_HW_DECODING "Set to ON to enable FFmpeg HW decoding" OFF)
option(DEINIT_ON_LAUNCH "Set to ON to deinitialize on game launch" OFF)
option(CLANG_TIDY "Set to ON to build using the clang-tidy static analyzer" OFF)
option(ASAN "Set to ON to build with AddressSanitizer" OFF)
option(TSAN "Set to ON to build with ThreadSanitizer" OFF)
option(UBSAN "Set to ON to build with UndefinedBehaviorSanitizer" OFF)

if(CLANG_TIDY)
    find_program(CLANG_TIDY_BINARY NAMES clang-tidy)
    if(CLANG_TIDY_BINARY MATCHES CLANG_TIDY_BINARY-NOTFOUND)
        message("-- CLANG_TIDY was set but the clang-tidy binary was not found")
    else()
        message("-- Building with the clang-tidy static analyzer")
        set(CMAKE_CXX_CLANG_TIDY "clang-tidy;-checks=*,\
                                  -fuchsia-*,\
                                  -hicpp-*,\
                                  -llvm-*,\
                                  -readability-braces-*,\
                                  -google-readability-braces-*,\
                                  -readability-uppercase-literal-suffix,\
                                  -modernize-use-trailing-return-type,\
                                  -cppcoreguidelines-avoid-magic-numbers,\
                                  -readability-magic-numbers")
    endif()
endif()

#---------------------------------------------------------------------------------------------------
# iOS build.


#---------------------------------------------------------------------------------------------------
# Emscripten WebAssembly build.


#---------------------------------------------------------------------------------------------------
# OpenGL setup.

if(GLES)
    set(GLSYSTEM "Embedded OpenGL" CACHE STRING "The OpenGL system to be used")
else()
    set(GLSYSTEM "Desktop OpenGL" CACHE STRING "The OpenGL system to be used")
endif()

set_property(CACHE GLSYSTEM PROPERTY STRINGS "Desktop OpenGL" "Embedded OpenGL")

#---------------------------------------------------------------------------------------------------
# Package dependencies.

if(GLSYSTEM MATCHES "Desktop OpenGL")
    set(OpenGL_GL_PREFERENCE GLVND)
    find_package(OpenGL REQUIRED)
elseif(ANDROID)
    find_package(OpenGLES3 REQUIRED)
elseif(GLES AND NOT IOS AND NOT EMSCRIPTEN)
    find_package(OpenGLES2 REQUIRED)
endif()

# On macOS, iOS and Windows all dependencies are kept in-tree in the "external" directory.
    find_package(CURL REQUIRED)
    find_package(FFmpeg REQUIRED)
    find_package(FreeImage REQUIRED)
    find_package(Freetype REQUIRED)
    find_package(HarfBuzz REQUIRED)
    find_package(ICU REQUIRED)
    find_package(Intl REQUIRED)
    find_package(Libgit2 REQUIRED)
    find_package(Pugixml REQUIRED)
    find_package(SDL2 REQUIRED)

# Add ALSA and BlueZ for Linux.
    find_package(ALSA REQUIRED)
    find_package(Bluez REQUIRED)

#---------------------------------------------------------------------------------------------------
# Compiler and linker settings.

if(CMAKE_CXX_COMPILER_ID MATCHES Clang)
    message("-- Compiler is Clang/LLVM")
    if(CMAKE_CXX_COMPILER_VERSION VERSION_LESS 5.0.0)
        message(SEND_ERROR "You need at least Clang 5.0.0 to compile Arcadia")
    endif()
elseif(CMAKE_CXX_COMPILER_ID MATCHES GNU)
    message("-- Compiler is GNU/GCC")
    if(CMAKE_CXX_COMPILER_VERSION VERSION_LESS 7.1)
        message(SEND_ERROR "You need at least GCC 7.1 to compile Arcadia")
    endif()
elseif(CMAKE_CXX_COMPILER_ID MATCHES MSVC)
    message("-- Compiler is MSVC")
    # Disable the built-in min() and max() macros.
    add_compile_definitions(NOMINMAX)
endif()

if(CMAKE_BUILD_TYPE)
    message("-- Build type is ${CMAKE_BUILD_TYPE}")
endif()

# Set up compiler and linker flags for debug, profiling or release builds.
if(CMAKE_BUILD_TYPE MATCHES Debug)
    # Enable the C++17 standard and disable optimizations as it's a debug build.
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++17 -O0 -g3 -Wall -Wpedantic -Wsign-compare -Wnarrowing -Wmissing-field-initializers -Wunused-macros")
        set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -O0")
    # If using Clang, then add additional debug data needed by GDB.
    # Comment this out if you're using LLDB for debugging as this flag makes the binary
    # much larger and the application much slower. On macOS this setting is never enabled
    # as LLDB is the default debugger on this OS.
    if(NOT APPLE AND CMAKE_CXX_COMPILER_ID MATCHES Clang)
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -D_GLIBCXX_DEBUG")
    endif()
elseif(CMAKE_BUILD_TYPE MATCHES Profiling)
    # For the profiling build, we enable optimizations and supply the required profiler flags.
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++17 -O2 -g3 -Wall -Wpedantic -Wsign-compare -Wnarrowing -Wmissing-field-initializers -Wunused-macros")
        set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -O2")
else()
    # Enable the C++17 standard and enable optimizations as it's a release build.
    # This will also disable all assert() macros. Strip the binary too.
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++17 -O2 -DNDEBUG -Wall -Wpedantic -Wsign-compare -Wnarrowing -Wmissing-field-initializers -Wunused-macros")
            set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -O2 -s")
endif()

# Silence some annoying warnings caused by invalid characters in some FreeImage source comments.
if(CMAKE_CXX_COMPILER_ID MATCHES Clang AND CMAKE_CXX_COMPILER_VERSION GREATER_EQUAL 15.0.0)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wno-invalid-utf8")
endif()



if(ASAN AND TSAN)
    message(FATAL_ERROR "-- AddressSanitizer and ThreadSanitizer can't be combined")
endif()

if(ASAN)
    message("-- Building with AddressSanitizer")
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fsanitize=address -fno-omit-frame-pointer")
endif()

if(TSAN)
    message("-- Building with ThreadSanitizer")
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fsanitize=thread -fno-omit-frame-pointer")
endif()

if(UBSAN)
    message("-- Building with UndefinedBehaviorSanitizer")
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fsanitize=undefined -fno-omit-frame-pointer")
endif()

if(ASAN OR UBSAN)
    # Add some extra checks when building with AddressSanitizer or UndefinedBehaviorSanitizer.
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -D_GLIBCXX_ASSERTIONS -D_FORTIFY_SOURCE=3")
endif()

# The following removes the ranlib warnings on macOS regarding missing symbols for files that have
# been #ifdef'ed away.




#---------------------------------------------------------------------------------------------------
# Preprocessor directives.

if(GLES)
    add_compile_definitions(USE_OPENGLES)
    message("-- Building with OpenGL ES renderer")
endif()

if(APPIMAGE_BUILD AND FLATPAK_BUILD)
    message(FATAL_ERROR "-- APPIMAGE_BUILD and FLATPAK_BUILD can't be combined")
endif()

if(APPIMAGE_BUILD)
    add_compile_definitions(APPIMAGE_BUILD)
    message("-- Building as an AppImage")
endif()

if(FLATPAK_BUILD)
    add_compile_definitions(FLATPAK_BUILD)
    message("-- Building as a Flatpak")
endif()

if(AUR_BUILD)
    message("-- Building for the AUR")
endif()

if(STEAM_DECK AND RETRODECK)
    message(FATAL_ERROR "-- STEAM_DECK and RETRODECK can't be combined")
endif()

if(STEAM_DECK)
    add_compile_definitions(STEAM_DECK)
    message("-- Building for the Valve Steam Deck")
endif()

if(RETRODECK)
    add_compile_definitions(RETRODECK)
    message("-- Building for RetroDECK")
endif()

if(BUNDLED_CERTS)
    add_compile_definitions(USE_BUNDLED_CERTIFICATES)
    message("-- Building with bundled TLS/SSL certificates")
endif()

if(VIDEO_HW_DECODING)
    add_compile_definitions(VIDEO_HW_DECODING)
    message("-- Building with FFmpeg HW decoding")
endif()

if(DEINIT_ON_LAUNCH)
        add_compile_definitions(DEINIT_ON_LAUNCH)
        message("-- Building with deinitialization on game launch")
endif()

if(AUR_BUILD OR FLATPAK_BUILD OR RETRODECK OR HAIKU OR IOS OR CMAKE_SYSTEM_NAME MATCHES FreeBSD)
    set(APPLICATION_UPDATER OFF)
endif()

if(APPLICATION_UPDATER)
    add_compile_definitions(APPLICATION_UPDATER)
else()
    message("-- Building without application updater")
endif()

if(CMAKE_SYSTEM_NAME MATCHES Linux AND CMAKE_SYSTEM_PROCESSOR MATCHES aarch64 AND NOT ANDROID)
    message("-- Building for Linux on ARM (AArch64)")
    add_compile_definitions(LINUX_AARCH64)
endif()



# Affects the application updater and is used for displaying version info in the main menu.
if(ES_VERSION MATCHES alpha OR ES_VERSION MATCHES beta OR ES_VERSION MATCHES dev)
    add_compile_definitions(IS_PRERELEASE)
endif()

# GLM library options.
add_compile_definitions(GLM_FORCE_CXX17)
add_compile_definitions(GLM_FORCE_XYZW_ONLY)

# For Unix systems, assign the installation prefix. If it's not explicitly set,
# we use /usr on Linux and /usr/local on FreeBSD.
    if(CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT)
            set(CMAKE_INSTALL_PREFIX /usr CACHE INTERNAL CMAKE_INSTALL_PREFIX)
    endif()
    message("-- Installation prefix is set to " ${CMAKE_INSTALL_PREFIX})
    add_compile_definitions(ES_INSTALL_PREFIX="${CMAKE_INSTALL_PREFIX}")

# For Windows, set the minimum OS version to Windows 7.

#---------------------------------------------------------------------------------------------------
# Include files.

set(COMMON_INCLUDE_DIRS ${CURL_INCLUDE_DIR}
                        ${CMAKE_CURRENT_SOURCE_DIR}/external/CImg
                        ${CMAKE_CURRENT_SOURCE_DIR}/external/glm
                        ${CMAKE_CURRENT_SOURCE_DIR}/external/lunasvg/include
                        ${CMAKE_CURRENT_SOURCE_DIR}/external/rapidjson/include
                        ${CMAKE_CURRENT_SOURCE_DIR}/external/rlottie/inc
                        ${CMAKE_CURRENT_SOURCE_DIR}/external/utfcpp/source
                        ${CMAKE_CURRENT_SOURCE_DIR}/es-core/src
                        ${CMAKE_CURRENT_SOURCE_DIR}/es-pdf-converter/src)
    set(COMMON_INCLUDE_DIRS ${COMMON_INCLUDE_DIRS}
                            ${BLUEZ_INCLUDE_DIRS}
                            ${FFMPEG_INCLUDE_DIRS}
                            ${FreeImage_INCLUDE_DIRS}
                            ${FREETYPE_INCLUDE_DIRS}
                            ${GIT2_INCLUDE_PATH}
                            ${HarfBuzz_INCLUDE_DIRS}
                            ${ICU_INCLUDE_DIRS}
                            ${PUGIXML_INCLUDE_DIRS}
                            ${SDL2_INCLUDE_DIR})

# For Linux, add the ALSA include directory.
    list(APPEND COMMON_INCLUDE_DIRS ${ALSA_INCLUDE_DIRS})

#---------------------------------------------------------------------------------------------------
# Dependency libraries.

    set(COMMON_LIBRARIES ${BLUEZ_LIBRARIES}
                         ${CURL_LIBRARIES}
                         ${FFMPEG_LIBRARIES}
                         ${FreeImage_LIBRARIES}
                         ${FREETYPE_LIBRARIES}
                         ${GIT2_LIBRARY}
                         ${HarfBuzz_LIBRARIES}
                         ${ICU_LIBRARIES}
                         ${PUGIXML_LIBRARIES}
                         ${SDL2_LIBRARY})
    if(Intl_LIBRARY)
        # On Unix systems where the gettext functions are not part of the C standard library
        # we need to explicitly link with the libintl library.
        set(COMMON_LIBRARIES ${COMMON_LIBRARIES} ${Intl_LIBRARY})
    endif()

    # SVG rendering library LunaSVG and Lottie animation library rlottie.
        set(COMMON_LIBRARIES ${COMMON_LIBRARIES} ${PROJECT_SOURCE_DIR}/liblunasvg.a)
        set(COMMON_LIBRARIES ${COMMON_LIBRARIES} ${PROJECT_SOURCE_DIR}/librlottie.a)


# Add ALSA for Linux libraries.
    list(APPEND COMMON_LIBRARIES ${ALSA_LIBRARY})

# OpenGL.
if(GLSYSTEM MATCHES "Desktop OpenGL")
    list(APPEND COMMON_LIBRARIES ${OPENGL_LIBRARIES})
elseif(GLES AND ANDROID)
    list(APPEND COMMON_LIBRARIES ${OPENGLES3_LIBRARIES})
elseif(GLES)
    list(APPEND COMMON_LIBRARIES ${OPENGLES2_LIBRARIES})
endif()

#---------------------------------------------------------------------------------------------------
# Build directories.

set(dir ${CMAKE_CURRENT_SOURCE_DIR})
set(EXECUTABLE_OUTPUT_PATH ${dir} CACHE PATH "Build directory" FORCE)
set(LIBRARY_OUTPUT_PATH ${dir} CACHE PATH "Build directory" FORCE)

if(COMPILE_LOCALIZATIONS)
    add_subdirectory(locale)
endif()

add_subdirectory(es-pdf-converter)
add_subdirectory(external)
add_subdirectory(es-core)
add_subdirectory(es-app)

# Make sure that es-pdf-convert is built first, and then that rlottie is built before es-core.
add_dependencies(lunasvg es-pdf-convert)

if(COMPILE_LOCALIZATIONS)
    add_dependencies(es-pdf-convert localization)
endif()

add_dependencies(es-core rlottie)

# Set lottie2gif to not be built.
set_target_properties(lottie2gif PROPERTIES EXCLUDE_FROM_ALL 1 EXCLUDE_FROM_DEFAULT_BUILD 1)
