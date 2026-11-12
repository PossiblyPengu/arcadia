//  SPDX-License-Identifier: MIT
//
//  ES-DE Frontend
//  PlatformUtil.cpp
//
//  Platform utility functions.
//

#define MAX_GAME_LOG_OUTPUT 5242880

#include "utils/PlatformUtil.h"

#include "InputManager.h"
#include "Log.h"
#include "Scripting.h"
#include "Window.h"

#include <SDL2/SDL.h>
#include <SDL2/SDL_events.h>

#include <unistd.h>


#include <array>
#include <fcntl.h>

namespace Utils
{
    namespace Platform
    {
        int runRebootCommand()
        {
            return system("shutdown --reboot now");
        }

        int runPoweroffCommand()
        {
            return system("shutdown --poweroff now");
        }

        int runSuspendCommand()
        {
            // This should work on all Linux distributions that use systemd.
            if (Utils::FileSystem::getPathToBinary("systemctl") != "")
                return system("systemctl suspend");

            // Fallback to the zzz command on some distributions.
            if (Utils::FileSystem::getPathToBinary("zzz") != "")
                return system("zzz");

            return -1;
        }

        int runSystemCommand(const std::string& cmd_utf8)
        {
            return system(cmd_utf8.c_str());
        }

        int runSystemCommand(const std::wstring& cmd_utf16)
        {
            return 0;
        }

        int launchGameUnix(const std::string& cmd_utf8,
                           const std::string& startDirectory,
                           bool runInBackground)
        {
            std::string command = std::string(cmd_utf8) + " 2>&1 &";

            // Launching games while keeping ES-DE running in the background is very crude as for
            // instance no output from the command is captured and no real error handling is
            // implemented. It should therefore only be used when absolutely necessary.
            if (runInBackground) {
                if (startDirectory != "")
                    command = "cd " + startDirectory + " && " + command;
                LOG(LogDebug)
                    << "Platform::launchGameUnix(): Launching game while keeping ES-DE running "
                       "in the background, no command output will be written to the log file";
                return system(command.c_str());
            }

            FILE* commandPipe;
            std::array<char, 128> buffer {};
            std::string commandOutput;
            int returnValue;

            if (startDirectory != "")
                command = "cd " + startDirectory + " && " + command;

            if (!(commandPipe = reinterpret_cast<FILE*>(popen(command.c_str(), "r")))) {
                LOG(LogError) << "Couldn't open pipe to command";
                return -1;
            }

            int fd {fileno(commandPipe)};
            fd_set readfds;
            struct timeval timeout;

            FD_ZERO(&readfds);
            FD_SET(fd, &readfds);
            timeout.tv_sec = 0;
            timeout.tv_usec = 10000;

            SDL_Event event {};

            // We're not completely suspended when launching a game, instead we'll continue to
            // poll events. As part of this we'll handle adding and removal of controllers, all
            // other events are discarded.
            while (true) {
                // Check if pipe is available for reading.
                if (select(fd + 1, &readfds, nullptr, nullptr, &timeout) != 0) {
                    if (fgets(buffer.data(), buffer.size(), commandPipe) != nullptr)
                        commandOutput.append(
                            commandOutput.length() < MAX_GAME_LOG_OUTPUT ? buffer.data() : "");
                    else
                        break;
                }
                FD_SET(fd, &readfds);
                timeout.tv_sec = 0;
                timeout.tv_usec = 10000;
                // Drop all events except those for adding and removing controllers.
                while (SDL_PollEvent(&event)) {
                    if (event.type == SDL_CONTROLLERDEVICEADDED ||
                        event.type == SDL_CONTROLLERDEVICEREMOVED)
                        InputManager::getInstance().parseEvent(event);
                }
            }

            returnValue = pclose(commandPipe);

            // We need to shift the return value as it contains some flags (which we don't need).
            returnValue >>= 8;

            const size_t commandOutputSize {commandOutput.size()};

            // Remove any trailing newline from the command output.
            if (commandOutput.size()) {
                if (commandOutput.back() == '\n')
                    commandOutput.pop_back();
            }

            if (returnValue) {
                LOG(LogError) << "launchGameUnix - return value "
                              << std::to_string(returnValue) + ":";
                if (commandOutput.size())
                    LOG(LogError) << commandOutput;
                else
                    LOG(LogError) << "No error output provided by game or emulator";
            }
            else if (commandOutput.size()) {
                LOG(LogDebug) << "Platform::launchGameUnix():";
                LOG(LogDebug) << "Output from launched game:\n" << commandOutput;
                if (commandOutputSize >= MAX_GAME_LOG_OUTPUT) {
                    LOG(LogWarning) << "Output was capped to " << commandOutputSize << " bytes";
                }
            }

            return returnValue;

        }

        int launchGameWindows(const std::wstring& cmd_utf16,
                              const std::wstring& startDirectory,
                              bool runInBackground,
                              bool hideWindow)
        {
            return 0;
        }

        unsigned int getTaskbarState()
        {
            return 0;
        }

        void hideTaskbar()
        {
        }

        void revertTaskbarState(unsigned int& state)
        {
        }

        int quitES(QuitMode mode)
        {
            sQuitMode = mode;

            SDL_Event quit {};
            quit.type = SDL_QUIT;
            SDL_PushEvent(&quit);
            return 0;
        }

        void processQuitMode()
        {
            switch (sQuitMode) {
                case QuitMode::REBOOT: {
                    LOG(LogInfo) << "Rebooting system";
                    Scripting::fireEvent("reboot");
                    Scripting::fireEvent("quit");
                    runRebootCommand();
                    break;
                }
                case QuitMode::POWEROFF: {
                    LOG(LogInfo) << "Powering off system";
                    Scripting::fireEvent("poweroff");
                    Scripting::fireEvent("quit");
                    runPoweroffCommand();
                    break;
                }
                default: {
                    Scripting::fireEvent("quit");
                    break;
                }
            }
        }

        void emergencyShutdown()
        {
            LOG(LogError) << "Critical - Performing emergency shutdown...";
            Scripting::fireEvent("quit");

            while (Window::getInstance()->getGuiStackSize() > 1 &&
                   Window::getInstance()->peekGui() != nullptr)
                delete Window::getInstance()->peekGui();
            Window::getInstance()->deinit();
            Log::flush();

            exit(EXIT_FAILURE);
        }

    } // namespace Platform

} // namespace Utils
