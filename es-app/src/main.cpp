//  SPDX-License-Identifier: MIT
//
//  Arcadia is a frontend for browsing and launching games from your multi-platform collection.
//
//  The column limit is 100 characters.
//  All Arcadia C++ source code is formatted using clang-format.
//
//  main.cpp
//
//  Main program loop. Interprets command-line arguments, checks for the home folder
//  and es_settings.xml configuration file, sets up the application environment and
//  starts listening to SDL events.
//

#include "ApplicationUpdater.h"
#include "ApplicationVersion.h"
#include "AudioManager.h"
#include "CollectionSystemsManager.h"
#include "InputManager.h"
#include "Log.h"
#include "MameNames.h"
#include "MediaViewer.h"
#include "PDFViewer.h"
#include "Screensaver.h"
#include "Scripting.h"
#include "Settings.h"
#include "Sound.h"
#include "SystemData.h"
#include "SystemStatus.h"
#include "guis/GuiDetectDevice.h"
#include "guis/GuiLaunchScreen.h"
#include "utils/FileSystemUtil.h"
#include "utils/LocalizationUtil.h"
#include "utils/PlatformUtil.h"
#include "utils/StringUtil.h"
#include "views/ViewController.h"

#include <SDL2/SDL_events.h>
#include <SDL2/SDL_timer.h>

// TODO: Not needed after moving to SDL3.
#include <SDL2/SDL_main.h>




#include <FreeImage.h>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <time.h>

namespace
{
    SDL_Event event {};
    Renderer* renderer {nullptr};
    Window* window {nullptr};
    int lastTime {0};


#if defined(APPLICATION_UPDATER)
    bool noUpdateCheck {false};
#endif
    bool forceInputConfig {false};
    bool createSystemDirectories {false};
    bool settingsNeedSaving {false};
    bool portableMode {false};

    enum loadSystemsReturnCode {
        LOADING_OK,
        INVALID_FILE,
        NO_ROMS
    };


} // namespace


// Steam Deck: in Game Mode (gamescope) Arcadia runs fullscreen as usual, but on a desktop (including
// the Deck's Desktop Mode) it opens in a normal window so it can be moved, closed and left alone.
// --fullscreen and --windowed override this, as does --resolution (which is always windowed).
void applyDisplayDefaults(bool forceFullscreen, bool forceWindowed)
{
    if (Settings::getInstance()->getInt("ScreenWidth") != 0 && !forceWindowed)
        return;
    const char* desktop {std::getenv("XDG_CURRENT_DESKTOP")};
    const bool gameMode {std::getenv("SteamGameId") != nullptr ||
                         std::getenv("GAMESCOPE_WAYLAND_DISPLAY") != nullptr ||
                         (desktop != nullptr && std::string(desktop) == "gamescope")};
    if (forceWindowed || (!forceFullscreen && !gameMode)) {
        // The window size is worked out once the display size is known (see Renderer), so that it
        // stays a window even on a screen the same size as the Deck's.
        if (Settings::getInstance()->getInt("ScreenWidth") == 0)
            Settings::getInstance()->setBool("DesktopWindow", true);
    }
}

bool parseArguments(const std::vector<std::string>& arguments)
{
    bool forceFullscreen {false};
    bool forceWindowed {false};
    Utils::FileSystem::setExePath(arguments[0]);
    const std::string portableFilePath {Utils::FileSystem::getExePath() + "/portable.txt"};

    // This is primarily intended for portable Arcadia installations on Windows (for example
    // placed on a USB memory stick) but it may be usable for other operating systems too.
    if (Utils::FileSystem::exists(portableFilePath)) {
        std::cout << "Found portable.txt in the Arcadia executable directory\n";
        std::ifstream portableFile;
        std::string homePath;
        portableFile.open(portableFilePath.c_str());
        if (!portableFile.fail()) {
            std::string relativePath;
            getline(portableFile, relativePath);
            // If the file is empty, use the Arcadia executable directory as home.
            if (relativePath == "")
                homePath = Utils::FileSystem::getExePath();
            else
                homePath = Utils::FileSystem::getExePath() + "/" + relativePath;

            bool homeExists {false};

            if (Utils::FileSystem::exists(homePath))
                homeExists = true;
            if (!homeExists) {
                std::cerr << "Error: Defined home path \"" << homePath << "\" does not exist\n";
            }
            else if (Utils::FileSystem::isRegularFile(homePath)) {
                std::cerr << "Error: Defined home path \"" << homePath << "\" is a file\n";
            }
            else {
                std::cout << "Setting home path to \"" << homePath << "\"\n";
                Utils::FileSystem::setHomePath(homePath);
                portableMode = true;
            }
        }
        portableFile.close();
    }

    // We need to process --home before any call to Settings::getInstance(), because
    // settings are loaded from the home path.
    for (size_t i {1}; i < arguments.size(); ++i) {
        if (arguments[i] == "--home") {
            if (i >= arguments.size() - 1) {
                std::cerr << "Error: No home path supplied with \'--home'\n";
                return false;
            }
            if (!Utils::FileSystem::exists(arguments[i + 1])) {
                std::cerr << "Error: Home path \'" << arguments[i + 1] << "\' does not exist\n";
                return false;
            }
            if (Utils::FileSystem::isRegularFile(arguments[i + 1])) {
                std::cerr << "Error: Home path \'" << arguments[i + 1]
                          << "\' is a file and not a directory\n";
                return false;
            }
            Utils::FileSystem::setHomePath(arguments[i + 1]);
            portableMode = false;
            break;
        }
    }

    for (size_t i {1}; i < arguments.size(); ++i) {
        // Skip past --home flag as we already processed it.
        if (arguments[i] == "--home") {
            ++i; // Skip the argument value.
            continue;
        }
        if (arguments[i] == "--display") {
            if (i >= arguments.size() - 1 || stoi(arguments[i + 1]) < 1 ||
                stoi(arguments[i + 1]) > 4) {
                std::cerr << "Error: Invalid display index supplied\n";
                return false;
            }
            const int displayIndex {stoi(arguments[i + 1])};
            Settings::getInstance()->setInt("DisplayIndex", displayIndex);
            settingsNeedSaving = true;
            ++i;
        }
        else if (arguments[i] == "--resolution") {
            if (i >= arguments.size() - 2) {
                std::cerr << "Error: Invalid resolution values supplied\n";
                return false;
            }
            const std::string widthArg {arguments[i + 1]};
            const std::string heightArg {arguments[i + 2]};
            if (widthArg.find_first_not_of("0123456789") != std::string::npos ||
                heightArg.find_first_not_of("0123456789") != std::string::npos) {
                std::cerr << "Error: Invalid resolution values supplied\n";
                return false;
            }
            const int width {stoi(arguments[i + 1])};
            const int height {stoi(arguments[i + 2])};
            if (width < 224 || height < 224 || width > 7680 || height > 7680 ||
                height < width / 4 || width < height / 3) {
                std::cerr << "Error: Unsupported resolution " << width << "x" << height
                          << " supplied\n";
                return false;
            }
            Settings::getInstance()->setInt("ScreenWidth", width);
            Settings::getInstance()->setInt("ScreenHeight", height);
            i += 2;
        }
        else if (arguments[i] == "--fullscreen") {
            forceFullscreen = true;
        }
        else if (arguments[i] == "--windowed") {
            forceWindowed = true;
        }
        else if (arguments[i] == "--screenoffset") {
            if (i >= arguments.size() - 2) {
                std::cerr << "Error: Invalid screenoffset values supplied\n";
                return false;
            }
            const int x {stoi(arguments[i + 1])};
            const int y {stoi(arguments[i + 2])};
            Settings::getInstance()->setInt("ScreenOffsetX", x);
            Settings::getInstance()->setInt("ScreenOffsetY", y);
            i += 2;
        }
        else if (arguments[i] == "--screenrotate") {
            if (i >= arguments.size() - 1) {
                std::cerr << "Error: No screenrotate value supplied\n";
                return false;
            }
            const std::string rotateValue {arguments[i + 1]};
            if (rotateValue != "0" && rotateValue != "90" && rotateValue != "180" &&
                rotateValue != "270") {
                std::cerr << "Error: Invalid screenrotate value supplied\n";
                return false;
            }
            Settings::getInstance()->setInt("ScreenRotate", stoi(arguments[i + 1]));
            settingsNeedSaving = true;
            ++i;
        }
        else if (arguments[i] == "--fullscreen-padding") {
            if (i >= arguments.size() - 1) {
                std::cerr << "Error: No fullscreen-padding value supplied\n";
                return false;
            }
            std::string fullscreenPaddingValue {arguments[i + 1]};
            if (fullscreenPaddingValue != "on" && fullscreenPaddingValue != "off" &&
                fullscreenPaddingValue != "1" && fullscreenPaddingValue != "0") {
                std::cerr << "Error: Invalid fullscreen-padding value supplied\n";
                return false;
            }
            const bool fullscreenPadding {
                (fullscreenPaddingValue == "on" || fullscreenPaddingValue == "1") ? true : false};
            Settings::getInstance()->setBool("FullscreenPadding", fullscreenPadding);
            ++i;
        }
        else if (arguments[i] == "--vsync") {
            if (i >= arguments.size() - 1) {
                std::cerr << "Error: No VSync value supplied\n";
                return false;
            }
            std::string vSyncValue {arguments[i + 1]};
            if (vSyncValue != "on" && vSyncValue != "off" && vSyncValue != "1" &&
                vSyncValue != "0") {
                std::cerr << "Error: Invalid VSync value supplied\n";
                return false;
            }
            const bool vSync {(vSyncValue == "on" || vSyncValue == "1") ? true : false};
            Settings::getInstance()->setBool("VSync", vSync);
            ++i;
        }
        else if (arguments[i] == "--max-vram") {
            if (i >= arguments.size() - 1) {
                std::cerr << "Error: Invalid VRAM value supplied\n";
                return false;
            }
            const int maxVRAM {stoi(arguments[i + 1])};
            Settings::getInstance()->setInt("MaxVRAM", maxVRAM);
            settingsNeedSaving = true;
            ++i;
        }
#if !defined(USE_OPENGLES)
        else if (arguments[i] == "--anti-aliasing") {
            bool invalidValue {false};
            int antiAlias {0};
            if (i >= arguments.size() - 1) {
                invalidValue = true;
            }
            else {
                antiAlias = stoi(arguments[i + 1]);
                if (antiAlias != 0 && antiAlias != 2 && antiAlias != 4)
                    invalidValue = true;
            }
            if (invalidValue) {
                std::cerr << "Error: Invalid anti-aliasing value supplied\n";
                return false;
            }
            Settings::getInstance()->setInt("AntiAliasing", antiAlias);
            settingsNeedSaving = true;
            ++i;
        }
#endif
        else if (arguments[i] == "--no-splash") {
            Settings::getInstance()->setBool("SplashScreen", false);
        }
#if defined(APPLICATION_UPDATER)
        else if (arguments[i] == "--no-update-check") {
            noUpdateCheck = true;
        }
#endif
        else if (arguments[i] == "--gamelist-only") {
            Settings::getInstance()->setBool("ParseGamelistOnly", true);
            settingsNeedSaving = true;
        }
        else if (arguments[i] == "--ignore-gamelist") {
            Settings::getInstance()->setBool("IgnoreGamelist", true);
        }
        else if (arguments[i] == "--show-hidden-files") {
            Settings::getInstance()->setBool("ShowHiddenFiles", true);
            settingsNeedSaving = true;
        }
        else if (arguments[i] == "--show-hidden-games") {
            Settings::getInstance()->setBool("ShowHiddenGames", true);
            settingsNeedSaving = true;
        }
        else if (arguments[i] == "--force-full") {
            Settings::getInstance()->setString("UIMode", "full");
            Settings::getInstance()->setBool("ForceFull", true);
        }
        else if (arguments[i] == "--force-kiosk") {
            Settings::getInstance()->setBool("ForceKiosk", true);
        }
        else if (arguments[i] == "--force-kid") {
            Settings::getInstance()->setBool("ForceKid", true);
        }
        else if (arguments[i] == "--force-input-config") {
            forceInputConfig = true;
        }
        else if (arguments[i] == "--create-system-dirs") {
            createSystemDirectories = true;
        }
        else if (arguments[i] == "--debug") {
            Settings::getInstance()->setBool("Debug", true);
            Settings::getInstance()->setBool("DebugFlag", true);
            Log::setReportingLevel(LogDebug);
        }
        else if (arguments[i] == "--version" || arguments[i] == "-v") {
            std::cout << "Arcadia " << PROGRAM_VERSION_STRING << " (r" << PROGRAM_RELEASE_NUMBER
                      << ")\n";
            return false;
        }
        else if (arguments[i] == "--help" || arguments[i] == "-h") {
            std::cout <<
                // clang-format off
"Usage: arcadia [options]\n"
"Arcadia Frontend\n\n"
"Options:\n"
"  --display [1 to 4]                    Display/monitor to use\n"
"  --resolution [width] [height]         Application resolution\n"
"  --fullscreen                          Always start fullscreen (the default in Game Mode)\n"
"  --windowed                            Always start in a window (the default on a desktop)\n"
"  --screenoffset [horiz.] [vert.]       Offset screen contents within application window\n"
"  --screenrotate [0, 90, 180 or 270]    Rotate screen contents within application window\n"
"  --fullscreen-padding [1/on or 0/off]  Padding if --resolution is lower than display resolution\n"
"  --vsync [1/on or 0/off]               Turn VSync on or off (default is on)\n"
"  --max-vram [size]                     Max VRAM to use (in mebibytes) before swapping\n"
#if !defined(USE_OPENGLES)
"  --anti-aliasing [0, 2 or 4]           Set MSAA anti-aliasing to disabled, 2x or 4x\n"
#endif
"  --no-splash                           Don't show the splash screen during startup\n"
#if defined(APPLICATION_UPDATER)
"  --no-update-check                     Don't check for application updates during startup\n"
#endif
"  --gamelist-only                       Skip automatic game search, only read from gamelist.xml\n"
"  --ignore-gamelist                     Ignore the gamelist.xml files\n"
"  --show-hidden-files                   Show hidden files and folders\n"
"  --show-hidden-games                   Show hidden games\n"
"  --force-full                          Force the UI mode to Full\n"
"  --force-kiosk                         Force the UI mode to Kiosk\n"
"  --force-kid                           Force the UI mode to Kid\n"
"  --force-input-config                  Force configuration of input devices\n"
"  --create-system-dirs                  Create game system directories\n"
"  --home [path]                         Directory to use as home path\n"
"  --debug                               Enable debug mode\n"
"  --version, -v                         Display version information\n"
"  --help, -h                            Summon a sentient, angry tuba\n";
            // clang-format on
            return false;
        }
        else {
            const std::string argUnknown {arguments[i]};
            std::cout << "Unknown option '" << argUnknown << "'.\n";
            std::cout << "Try 'arcadia --help' for more information.\n";
            return false;
        }
    }

    if (Settings::getInstance()->getBool("IgnoreGamelist")) {
        Settings::getInstance()->setBool("ParseGamelistOnly", false);
        settingsNeedSaving = true;
    }

    applyDisplayDefaults(forceFullscreen, forceWindowed);

    return true;
}

bool checkApplicationDataDirectory()
{
    // Check that the application data directory exists, otherwise create it.
    const std::string applicationData {Utils::FileSystem::getAppDataDirectory()};
    if (!Utils::FileSystem::exists(applicationData)) {
        std::cout << "First startup, creating application data directory \"" << applicationData
                  << "\"\n";
        Utils::FileSystem::createDirectory(applicationData);
        if (!Utils::FileSystem::exists(applicationData)) {
            std::cerr << "Error: Couldn't create directory, permission problems?\n";
            return false;
        }
    }

    return true;
}

loadSystemsReturnCode loadSystemConfigFile()
{
    if (SystemData::loadConfig())
        return INVALID_FILE;

    if (SystemData::sSystemVector.size() == 0) {
        LOG(LogInfo) << "No game files were found, make sure that the system directories are "
                        "setup correctly and that the file extensions are supported";
        return NO_ROMS;
    }

    return LOADING_OK;
}

void onExit()
{
    // Called on exit, assuming we get far enough to have the log initialized.
    Log::close();
}

void applicationLoop()
{
    while (true) {
        if (SDL_PollEvent(&event)) {
            do {
                InputManager::getInstance().parseEvent(event);

                if (event.type == SDL_QUIT)
                    return;
            } while (SDL_PollEvent(&event));
        }

        int curTime {static_cast<int>(SDL_GetTicks())};
        int deltaTime {curTime - lastTime};
        lastTime = curTime;

        // Cap deltaTime if it ever goes negative.
        if (deltaTime < 0)
            deltaTime = 1000;

        window->update(deltaTime);
        window->render();

        renderer->swapBuffers();
        Log::flush();
    }
}

int main(int argc, char* argv[])
{
    const auto applicationStartTime {std::chrono::system_clock::now()};

    std::locale::global(std::locale("C"));

    SDL_SetHint(SDL_HINT_APP_NAME, "Arcadia");



    {
        std::vector<std::string> arguments;
        for (int i {0}; i < argc; ++i)
            arguments.emplace_back(argv[i]);
        if (!parseArguments(arguments)) {
            return 0;
        }
    }


    if (!Settings::getInstance()->getBool("DebugFlag") &&
        Settings::getInstance()->getBool("DebugMode")) {
        Settings::getInstance()->setBool("Debug", true);
        Log::setReportingLevel(LogDebug);
    }

#if defined(FREEIMAGE_LIB)
    // Call this ONLY when linking with FreeImage as a static library.
    FreeImage_Initialise();
#endif

    // If the application data directory doesn't exist and can't be created, then exit.
    if (!checkApplicationDataDirectory())
        return 1;

    {
        // Create the logs folder in the application data directory.
        const std::string logsDir {Utils::FileSystem::getAppDataDirectory() + "/logs"};
        if (!Utils::FileSystem::isDirectory(logsDir)) {
            std::cout << "Creating logs directory \"" << logsDir << "\"..." << std::endl;
            Utils::FileSystem::createDirectory(logsDir);
            if (!Utils::FileSystem::isDirectory(logsDir)) {
                std::cerr << "Couldn't create directory, permission problems?" << std::endl;
            }
            else {
                // Remove any old logs in the root of the directory.
                Utils::FileSystem::removeFile(Utils::FileSystem::getAppDataDirectory() +
                                              "/es_log.txt");
                Utils::FileSystem::removeFile(Utils::FileSystem::getAppDataDirectory() +
                                              "/es_log.txt.bak");
            }
        }
    }

    // Start the logger.
    Log::init();
    Log::open();
    {
        const std::string applicationName {"Arcadia"};
        LOG(LogInfo) << applicationName << " " << PROGRAM_VERSION_STRING << " (r"
                     << PROGRAM_RELEASE_NUMBER << "), built " << PROGRAM_BUILT_STRING;
        if (portableMode) {
            LOG(LogInfo) << "Running in portable mode";
            Settings::getInstance()->setBool("PortableMode", true);
        }
        else {
            Settings::getInstance()->setBool("PortableMode", false);
        }
    }

    // Always close the log on exit.
    atexit(&onExit);

    if (createSystemDirectories) {
        if (!SystemData::createSystemDirectories() && !Settings::getInstance()->getBool("Debug"))
            std::cout << "System directories successfully created" << std::endl;
        LOG(LogInfo) << "Arcadia cleanly shutting down";
        return 0;
    }

    Scripting::fireEvent("startup");


    bool migratedSettings {false};

    {
        // Create the settings folder in the application data directory.
        const std::string settingsDir {Utils::FileSystem::getAppDataDirectory() + "/settings"};
        if (!Utils::FileSystem::isDirectory(settingsDir)) {
            LOG(LogInfo) << "Creating settings directory \"" << settingsDir << "\"...";
            Utils::FileSystem::createDirectory(settingsDir);
            if (!Utils::FileSystem::isDirectory(settingsDir)) {
                LOG(LogError) << "Couldn't create directory, permission problems?";
            }
        }
        std::string settingsPathOld;
        std::string settingsPathNew;
        settingsPathOld = Utils::FileSystem::getAppDataDirectory() + "/es_settings.xml";
        settingsPathNew = Utils::FileSystem::getAppDataDirectory() + "/settings/es_settings.xml";
        if (!Utils::FileSystem::exists(settingsPathNew) &&
            Utils::FileSystem::exists(settingsPathOld)) {
            Utils::FileSystem::renameFile(settingsPathOld, settingsPathNew, false);
            Settings::getInstance()->loadFile();
            migratedSettings = true;
        }
        settingsPathOld = Utils::FileSystem::getAppDataDirectory() + "/es_input.xml";
        settingsPathNew = Utils::FileSystem::getAppDataDirectory() + "/settings/es_input.xml";
        if (!Utils::FileSystem::exists(settingsPathNew) &&
            Utils::FileSystem::exists(settingsPathOld)) {
            Utils::FileSystem::renameFile(settingsPathOld, settingsPathNew, false);
            migratedSettings = true;
        }
    }

    {
        // Check if the es_settings.xml file exists, and if not, create it.
        std::string settingsPath {Utils::FileSystem::getAppDataDirectory() +
                                  "/settings/es_settings.xml"};

        if (!Utils::FileSystem::exists(settingsPath)) {
            LOG(LogInfo) << "Settings file es_settings.xml does not exist, creating it...";
            Settings::getInstance()->saveFile();
        }
        else if (settingsNeedSaving) {
            LOG(LogInfo) << "Saving settings that were modified by command line options...";
            Settings::getInstance()->saveFile();
        }
    }


    {
        // Check if the application release number has changed, which would normally mean that the
        // user has upgraded to a new version.
        int applicationRelease;
        if ((applicationRelease = Settings::getInstance()->getInt("ApplicationRelease")) !=
            PROGRAM_RELEASE_NUMBER) {
            if (applicationRelease != 0) {
                LOG(LogInfo) << "Application release number changed from previous startup, from \""
                             << applicationRelease << "\" to \"" << PROGRAM_RELEASE_NUMBER << "\"";
            }
            else {
                LOG(LogInfo) << "Application release number setting is blank, changing it to \""
                             << PROGRAM_RELEASE_NUMBER << "\"";
            }
            Settings::getInstance()->setInt("ApplicationRelease", PROGRAM_RELEASE_NUMBER);
            Settings::getInstance()->saveFile();
        }
    }

    {
        // Create the gamelists folder in the application data directory.
        const std::string gamelistsDir {Utils::FileSystem::getAppDataDirectory() + "/gamelists"};
        if (!Utils::FileSystem::exists(gamelistsDir)) {
            LOG(LogInfo) << "Creating gamelists directory \"" << gamelistsDir << "\"...";
            Utils::FileSystem::createDirectory(gamelistsDir);
            if (!Utils::FileSystem::exists(gamelistsDir)) {
                LOG(LogWarning) << "Couldn't create directory, permission problems?";
            }
        }
    }

    {
        // Create the game media folder.
        const std::string mediaDirectory {FileData::getMediaDirectory()};
        if (!Utils::FileSystem::exists(mediaDirectory)) {
            LOG(LogInfo) << "Creating game media directory \"" << mediaDirectory << "\"...";
            Utils::FileSystem::createDirectory(mediaDirectory);
            if (!Utils::FileSystem::exists(mediaDirectory)) {
                LOG(LogWarning) << "Couldn't create directory, permission problems?";
            }
        }
    }

    {
        // Create the themes folder in the application data directory (or elsewhere if the
        // UserThemeDirectory setting has been defined).
        const std::string defaultUserThemeDir {Utils::FileSystem::getAppDataDirectory() +
                                               "/themes"};
        std::string userThemeDirSetting {Utils::FileSystem::expandHomePath(
            Settings::getInstance()->getString("UserThemeDirectory"))};
        std::string userThemeDirectory;

        if (userThemeDirSetting.empty())
            userThemeDirectory = defaultUserThemeDir;
        else
            userThemeDirectory = userThemeDirSetting;

        if (!Utils::FileSystem::exists(userThemeDirectory)) {
            LOG(LogInfo) << "Creating themes directory \"" << userThemeDirectory << "\"...";
            Utils::FileSystem::createDirectory(userThemeDirectory);
            if (!Utils::FileSystem::exists(userThemeDirectory)) {
                LOG(LogWarning) << "Couldn't create directory, permission problems?";
            }
        }
    }

    {
    }

    {
        // Create the scripts folder in the application data directory. This is only required
        // for custom event scripts so it's also created as a convenience.
        const std::string scriptsDir {Utils::FileSystem::getAppDataDirectory() + "/scripts"};
        if (!Utils::FileSystem::exists(scriptsDir)) {
            LOG(LogInfo) << "Creating scripts directory \"" << scriptsDir << "\"...";
            Utils::FileSystem::createDirectory(scriptsDir);
            if (!Utils::FileSystem::exists(scriptsDir)) {
                LOG(LogWarning) << "Couldn't create directory, permission problems?";
            }
        }
    }

    {
        // Create the screensavers and screensavers/custom_slideshow directories.
        const std::string screensaversDir {Utils::FileSystem::getAppDataDirectory() +
                                           "/screensavers"};
        const std::string slideshowDir {Utils::FileSystem::getAppDataDirectory() +
                                        "/screensavers/custom_slideshow"};
        if (!Utils::FileSystem::exists(screensaversDir)) {
            LOG(LogInfo) << "Creating screensavers directory \"" << screensaversDir << "\"...";
            Utils::FileSystem::createDirectory(screensaversDir);
            if (!Utils::FileSystem::exists(screensaversDir)) {
                LOG(LogWarning) << "Couldn't create directory, permission problems?";
            }
        }
        if (!Utils::FileSystem::exists(slideshowDir)) {
            LOG(LogInfo) << "Creating custom_slideshow directory \"" << slideshowDir << "\"...";
            Utils::FileSystem::createDirectory(slideshowDir);
            if (!Utils::FileSystem::exists(slideshowDir)) {
                LOG(LogWarning) << "Couldn't create directory, permission problems?";
            }
        }
    }

    {
        // Create the controllers folder in the application data directory.
        const std::string controllersDir {Utils::FileSystem::getAppDataDirectory() +
                                          "/controllers"};
        if (!Utils::FileSystem::exists(controllersDir)) {
            LOG(LogInfo) << "Creating controllers directory \"" << controllersDir << "\"...";
            Utils::FileSystem::createDirectory(controllersDir);
            if (!Utils::FileSystem::exists(controllersDir)) {
                LOG(LogWarning) << "Couldn't create directory, permission problems?";
            }
        }
        std::string configPathOld {Utils::FileSystem::getAppDataDirectory() +
                                   "/es_controller_mappings.cfg"};
        std::string configPathNew {Utils::FileSystem::getAppDataDirectory() +
                                   "/controllers/es_controller_mappings.cfg"};
        if (!Utils::FileSystem::exists(configPathNew) && Utils::FileSystem::exists(configPathOld)) {
            Utils::FileSystem::renameFile(configPathOld, configPathNew, false);
            migratedSettings = true;
        }
    }


    Utils::Localization::setLocale();

    renderer = Renderer::getInstance();
    window = Window::getInstance();

    ViewController::getInstance()->setMenuColors();
    CollectionSystemsManager::getInstance();
    Screensaver screensaver;
    MediaViewer mediaViewer;
    PDFViewer pdfViewer;
    GuiLaunchScreen guiLaunchScreen;

    if (!window->init()) {
        LOG(LogError) << "Window failed to initialize";
        return 1;
    }



#if defined(APPLICATION_UPDATER)
    if (!noUpdateCheck)
        ApplicationUpdater::getInstance().checkForUpdates();
#endif

    window->pushGui(ViewController::getInstance());

    if (Settings::getInstance()->getBool("SplashScreen"))
        window->renderSplashScreen(Window::SplashScreenState::SCANNING, 0.0f);

    while (SDL_PollEvent(&event)) {};


    AudioManager::getInstance();

    SDL_version version;
    SDL_GetVersion(&version);

    LOG(LogInfo) << "SDL version: " << std::to_string(version.major) << "."
                 << std::to_string(version.minor) << "." << std::to_string(version.patch);

    if (version.major > 2 || (version.major == 2 && version.minor >= 28)) {
        // This will prevent the popup virtual keyboard of any handheld device from being
        // automatically displayed on top of the Arcadia virtual keyboard.
#define SDL_HINT_ENABLE_SCREEN_KEYBOARD "SDL_ENABLE_SCREEN_KEYBOARD"
        SDL_SetHint(SDL_HINT_ENABLE_SCREEN_KEYBOARD, "0");
    }

    SystemStatus::getInstance();
    MameNames::getInstance();
    ThemeData::populateThemes();
    loadSystemsReturnCode loadSystemsStatus {loadSystemConfigFile()};

    if (!SystemData::sStartupExitSignal) {
        if (loadSystemsStatus) {
            // If there was an issue parsing the es_systems.xml file, display an error message.
            // If there were no game files found, give the option to the user to quit or to
            // configure a different ROM directory as well as to generate the game systems
            // directory structure.
            if (loadSystemsStatus == INVALID_FILE) {
                ViewController::getInstance()->invalidSystemsFileDialog();
            }
            else if (loadSystemsStatus == NO_ROMS) {
                ViewController::getInstance()->noGamesDialog();
            }
        }

        // Don't generate controller events while we're loading.
        SDL_GameControllerEventState(SDL_DISABLE);

        // Preload system view and all gamelist views.
        ViewController::getInstance()->preload();
    }

    if (!SystemData::sStartupExitSignal) {
        if (loadSystemsStatus == loadSystemsReturnCode::LOADING_OK)
            ThemeData::themeLoadedLogOutput();

        if (!loadSystemsStatus)
            ViewController::getInstance()->goToStart(true);

        // Check if any of the enabled systems have an invalid alternative emulator entry,
        // which means that a label is present in the gamelist.xml file which is not matching
        // any command tag in es_systems.xml.
        for (auto system : SystemData::sSystemVector) {
            if (system->getAlternativeEmulator().substr(0, 9) == "<INVALID>") {
                ViewController::getInstance()->invalidAlternativeEmulatorDialog();
                break;
            }
        }


        // Generate controller events since we're done loading.
        SDL_GameControllerEventState(SDL_ENABLE);

        lastTime = SDL_GetTicks();

#if defined(APPLICATION_UPDATER)
        if (ApplicationUpdater::getInstance().getResults())
            ViewController::getInstance()->updateAvailableDialog();
        else
            HttpReq::cleanupCurlMulti();
#endif


        if (migratedSettings) {
            LOG(LogInfo) << "Migrated settings from a legacy application data directory structure";
            ViewController::getInstance()->migratedAppDataFilesDialog();
        }

        LOG(LogInfo) << "Application startup time: "
                     << std::chrono::duration_cast<std::chrono::milliseconds>(
                            std::chrono::system_clock::now() - applicationStartTime)
                            .count()
                     << " ms";

        // Open the input configuration GUI if the force flag was passed from the command line.
        if (forceInputConfig) {
            ViewController::getInstance()->cancelViewTransitions();
            window->pushGui(new GuiDetectDevice(false, true, nullptr));
        }

        // Main application loop.


        if (!SystemData::sStartupExitSignal) {
            applicationLoop();
        }
    }
    else {
        LOG(LogInfo) << "Exit signal received, aborting application startup";
    }

    while (window->peekGui() != ViewController::getInstance())
        delete window->peekGui();
    window->deinit();

    HttpReq::cleanupCurlMulti();
    TextureResource::setExit();
    CollectionSystemsManager::getInstance()->deinit(true);
    SystemData::deleteSystems();
    NavigationSounds::getInstance().deinit();

#if defined(FREEIMAGE_LIB)
    // Call this ONLY when linking with FreeImage as a static library.
    FreeImage_DeInitialise();
#endif


    Utils::Platform::processQuitMode();

    LOG(LogInfo) << "Arcadia cleanly shutting down";



    return 0;
}
