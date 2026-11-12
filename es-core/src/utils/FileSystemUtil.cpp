//  SPDX-License-Identifier: MIT
//
//  Arcadia Frontend
//  FileSystemUtil.cpp
//
//  Low-level filesystem functions.
//  Resolve relative paths, resolve symlinks, create directories,
//  remove files etc.
//



#include "utils/FileSystemUtil.h"

#include "Log.h"
#include "utils/PlatformUtil.h"
#include "utils/StringUtil.h"

#include <fstream>
#include <regex>
#include <string>
#include <sys/stat.h>

#include <dirent.h>
#include <unistd.h>

// For Unix systems, set the install prefix as defined via CMAKE_INSTALL_PREFIX when CMake was run.
// If not defined, the default prefix "/usr" will be used on Linux and "/usr/local" on FreeBSD.
// This fallback should not be required though unless the build environment is broken.
#if defined(ES_INSTALL_PREFIX)
const std::string installPrefix {ES_INSTALL_PREFIX};
#else
const std::string installPrefix {"/usr"};
#endif

namespace Utils
{
    namespace FileSystem
    {
        static std::string homePath;
        static std::string exePath;
        static std::string esBinary;

        StringList getDirContent(const std::string& path, const bool recursive)
        {
            const std::string& genericPath {getGenericPath(path)};
            StringList contentList;

            if (!isDirectory(genericPath))
                return contentList;

            try {
                if (recursive) {
                    for (auto& entry : std::filesystem::recursive_directory_iterator(genericPath)) {
                        contentList.emplace_back(entry.path().generic_string());
                    }
                }
                else {
                    for (auto& entry : std::filesystem::directory_iterator(genericPath)) {
                        contentList.emplace_back(entry.path().generic_string());
                    }
                }
            }
            catch (...) {
                LOG(LogError) << "FileSystemUtil::getDirContent(): Couldn't read directory " << "\""
                              << path << "\", permission problems?";
                return contentList;
            }

            contentList.sort();
            return contentList;
        }

        StringList getMatchingFiles(const std::string& pattern)
        {
            StringList files;
            size_t entry {pattern.find('*')};

            if (entry == std::string::npos)
                return files;

            const std::string& parent {getParent(pattern)};

            // Don't allow wildcard matching for the parent directory.
            if (entry <= parent.size())
                return files;

            const StringList& dirContent {getDirContent(parent)};

            if (dirContent.size() == 0)
                return files;

            // Some characters need to be escaped in order for the regular expression to work.
            std::string escPattern {Utils::String::replace(pattern, "*", ".*")};
            escPattern = Utils::String::replace(escPattern, ")", "\\)");
            escPattern = Utils::String::replace(escPattern, "(", "\\(");
            escPattern = Utils::String::replace(escPattern, "]", "\\]");
            escPattern = Utils::String::replace(escPattern, "[", "\\[");

            std::regex expression;

            try {
                expression = escPattern;
            }
            catch (...) {
                LOG(LogError) << "FileSystemUtil::getMatchingFiles(): Invalid regular expression "
                              << "\"" << pattern << "\"";
                return files;
            }

            for (auto& entry : dirContent) {
                if (std::regex_match(entry, expression))
                    files.emplace_back(entry);
            }

            return files;
        }

        StringList getPathList(const std::string& path)
        {
            StringList pathList;
            const std::string& genericPath {getGenericPath(path)};
            size_t start {0};
            size_t end {0};

            // Split at '/'
            while ((end = genericPath.find("/", start)) != std::string::npos) {
                if (end != start)
                    pathList.emplace_back(std::string {genericPath, start, end - start});
                start = end + 1;
            }
            // Add last folder / file to pathList.
            if (start != genericPath.size())
                pathList.emplace_back(std::string {genericPath, start, genericPath.size() - start});

            return pathList;
        }

        void setHomePath(const std::string& path)
        {
            // Set home path.
            homePath = getGenericPath(path);
        }

        std::string getHomePath()
        {
            // Only construct the homepath once.
            if (homePath.length())
                return homePath;



            if (!homePath.length()) {
                std::string envHome;
                if (getenv("HOME") != nullptr)
                    envHome = getenv("HOME");
                if (envHome.length())
                    homePath = getGenericPath(envHome);
            }

            // No homepath found, fall back to current working directory.
            if (!homePath.length())
                homePath = getCWDPath();

            return homePath;
        }

        std::string getSystemHomeDirectory()
        {
            std::string envHome;
            if (getenv("HOME") != nullptr)
                envHome = getenv("HOME");
            return envHome;
            return "";
        }

        std::string getAppDataDirectory()
        {

            if (FileSystemVariables::sAppDataDirectory.empty()) {
                if (getenv("ESDE_APPDATA_DIR") != nullptr) {
                    const std::string envAppDataDir {getenv("ESDE_APPDATA_DIR")};
                    FileSystemVariables::sAppDataDirectory = expandHomePath(envAppDataDir);
                }
                else if (Utils::FileSystem::exists(getHomePath() + "/Arcadia")) {
                    FileSystemVariables::sAppDataDirectory = getHomePath() + "/Arcadia";
                }
                else {
                    FileSystemVariables::sAppDataDirectory = getHomePath() + "/Arcadia";
                }
            }

            return FileSystemVariables::sAppDataDirectory;
        }

        std::string getInternalAppDataDirectory()
        {
            return "";
        }

        std::string getCWDPath()
        {
            // Return current working directory.

            char temp[512];
            return (getcwd(temp, 512) ? getGenericPath(temp) : "");
        }

        std::string getPathToBinary(const std::string& executable)
        {
#if defined(FLATPAK_BUILD)
            // Ugly hack to compensate for the Flatpak sandbox restrictions. We traverse
            // this hardcoded list of paths and use the "which" command to check outside the
            // sandbox if the emulator binary exists.
            const std::string& pathVariable {
                "/var/lib/flatpak/exports/bin:/usr/bin:/usr/local/"
                "bin:/usr/local/sbin:/usr/sbin:/sbin:/bin:/usr/games:/usr/"
                "local/games:/snap/bin:/var/lib/snapd/snap/bin"};

            const std::vector<std::string>& pathList {
                Utils::String::delimitedStringToVector(pathVariable, ":")};

            // Using a temporary file is the only viable solution I've found to communicate
            // between the sandbox and the outside world.
            const std::string& tempFile {Utils::FileSystem::getAppDataDirectory() +
                                         "/.flatpak_emulator_binary_path.tmp"};

            std::string emulatorPath;

            for (auto it = pathList.cbegin(); it != pathList.cend(); ++it) {
                Utils::Platform::runSystemCommand("flatpak-spawn --host which " + *it + "/" +
                                                  executable + " > " + tempFile + " 2>/dev/null");
                std::ifstream tempFileStream;
                tempFileStream.open(tempFile, std::ios::binary);
                getline(tempFileStream, emulatorPath);
                tempFileStream.close();

                if (emulatorPath != "") {
                    emulatorPath = getParent(emulatorPath);
                    break;
                }
            }

            if (Utils::FileSystem::exists(tempFile))
                removeFile(tempFile);

            return emulatorPath;
#else
            std::string envPath;
            if (getenv("PATH") != nullptr)
                envPath = getenv("PATH");

            const std::vector<std::string>& pathList {
                Utils::String::delimitedStringToVector(envPath, ":")};

            std::string pathTest;

            for (auto it = pathList.cbegin(); it != pathList.cend(); ++it) {
                pathTest = it->c_str() + ("/" + executable);
                if (Utils::FileSystem::isRegularFile(pathTest) ||
                    Utils::FileSystem::isSymlink(pathTest))
                    return it->c_str();
            }
            return "";
#endif
        }

        void setExePath(const std::string& path)
        {
            constexpr int pathMax {32767};
            std::string result(pathMax, 0);
            if (readlink("/proc/self/exe", &result[0], pathMax) != -1)
                exePath = result;
            exePath.erase(std::find(exePath.begin(), exePath.end(), '\0'), exePath.end());
            esBinary = exePath;
            exePath = getCanonicalPath(exePath);

            // Fallback to argv[0] if everything else fails, which is always the case on macOS.
            if (exePath.empty()) {
                esBinary = path;
                exePath = getCanonicalPath(path);
            }
            if (isRegularFile(exePath))
                exePath = getParent(exePath);

#if defined(APPIMAGE_BUILD)
            // We need to check that the APPIMAGE variable is available as the APPIMAGE_BUILD
            // build flag could have been passed without running as an actual AppImage.
            if (getenv("APPIMAGE") != nullptr)
                esBinary = getenv("APPIMAGE");
#endif
        }

        std::string getExePath()
        {
            // Return executable path.
            return exePath;
        }

        std::string getEsBinary()
        {
            // Return the absolute path to the Arcadia binary.
            return esBinary;
        }

        std::string getProgramDataPath()
        {
    return installPrefix + "/share/arcadia";
        }

        std::string getPreferredPath(const std::string& path)
        {
            const std::string& preferredPath {path};
            return preferredPath;
        }

        std::string getGenericPath(const std::string& path)
        {
            std::string genericPath {path};
            size_t offset {std::string::npos};

            // Remove "\\\\?\\"
            if ((genericPath.find("\\\\?\\")) == 0)
                genericPath.erase(0, 4);

            // Convert '\\' to '/'
            while ((offset = genericPath.find('\\')) != std::string::npos)
                genericPath.replace(offset, 1, "/");

            // Remove double '/'
            while ((offset = genericPath.find("//")) != std::string::npos)
                genericPath.erase(offset, 1);

            // Remove trailing '/' when the path is more than a simple '/'
            while (genericPath.length() > 1 &&
                   ((offset = genericPath.find_last_of('/')) == (genericPath.length() - 1)))
                genericPath.erase(offset, 1);

            return genericPath;
        }

        std::string getEscapedPath(const std::string& path)
        {
            std::string escapedPath {getGenericPath(path)};

            // Insert a backslash before most characters that would mess up a bash path.
            const char* invalidChars {"\\ '\"!$^&*(){}[]?;<>"};
            const char* invalidChar {invalidChars};

            while (*invalidChar) {
                size_t start {0};
                size_t offset {0};

                while ((offset = escapedPath.find(*invalidChar, start)) != std::string::npos) {
                    start = offset + 1;

                    if ((offset == 0) || (escapedPath[offset - 1] != '\\')) {
                        escapedPath.insert(offset, 1, '\\');
                        ++start;
                    }
                }
                ++invalidChar;
            }
            return escapedPath;
        }

        std::string getCanonicalPath(const std::string& path)
        {
            // Hack for builtin resources.
            if ((path[0] == ':') && (path[1] == '/'))
                return path;

            std::string canonicalPath {Utils::FileSystem::exists(path) ? getAbsolutePath(path) :
                                                                         getGenericPath(path)};

            // Cleanup path.
            bool scan {true};
            while (scan) {
                const StringList& pathList {getPathList(canonicalPath)};

                canonicalPath.clear();
                scan = false;

                for (StringList::const_iterator it {pathList.cbegin()}; it != pathList.cend();
                     ++it) {
                    // Ignore empty.
                    if ((*it).empty())
                        continue;

                    // Remove "/./"
                    if ((*it) == ".")
                        continue;

                    // Resolve "/../"
                    if ((*it) == "..") {
                        canonicalPath = getParent(canonicalPath);
                        continue;
                    }

                    // Append folder to path.
                    canonicalPath += ("/" + (*it));

                    if (isSymlink(canonicalPath)) {
                        const std::string& resolved {resolveSymlink(canonicalPath)};

                        if (resolved.empty())
                            return "";

                        if (isAbsolute(resolved))
                            canonicalPath = resolved;
                        else
                            canonicalPath = getParent(canonicalPath) + "/" + resolved;

                        for (++it; it != pathList.cend(); ++it)
                            canonicalPath += (canonicalPath.size() == 0) ? (*it) : ("/" + (*it));

                        scan = true;
                        break;
                    }
                }
            }
            return canonicalPath;
        }

        std::string getAbsolutePath(const std::string& path, const std::string& base)
        {
            const std::string& absolutePath {getGenericPath(path)};
            const std::string& baseVar {isAbsolute(base) ? getGenericPath(base) :
                                                           getAbsolutePath(base)};

            return isAbsolute(absolutePath) ? absolutePath :
                                              getGenericPath(baseVar + "/" + absolutePath);
        }

        std::string getParent(const std::string& path)
        {
            std::string genericPath {getGenericPath(path)};
            size_t offset {std::string::npos};

            // Find last '/' and erase it.
            if ((offset = genericPath.find_last_of('/')) != std::string::npos)
                return genericPath.erase(offset);

            // No parent found.
            return genericPath;
        }

        std::string getFileName(const std::string& path)
        {
            const std::string& genericPath {getGenericPath(path)};
            size_t offset {std::string::npos};

            // Find last '/' and return the filename.
            if ((offset = genericPath.find_last_of('/')) != std::string::npos)
                return ((genericPath[offset + 1] == 0) ? "." :
                                                         std::string {genericPath, offset + 1});

            // No '/' found, entire path is a filename.
            return genericPath;
        }

        std::string getStem(const std::string& path)
        {
            std::string fileName {getFileName(path)};
            size_t offset {std::string::npos};

            // Empty fileName.
            if (fileName == ".")
                return fileName;

            if (!Utils::FileSystem::isDirectory(path)) {
                // Find last '.' and erase the extension.
                if ((offset = fileName.find_last_of('.')) != std::string::npos)
                    return fileName.erase(offset);
            }

            // No '.' found, filename has no extension.
            return fileName;
        }

        std::string getExtension(const std::string& path)
        {
            const std::string& fileName {getFileName(path)};
            size_t offset {std::string::npos};

            // Empty fileName.
            if (fileName == ".")
                return fileName;

            // Find last '.' and return the extension.
            if ((offset = fileName.find_last_of('.')) != std::string::npos)
                return std::string {fileName, offset};

            // No '.' found, filename has no extension.
            return ".";
        }

        long getFileSize(const std::filesystem::path& path)
        {
            try {
                return static_cast<long>(std::filesystem::file_size(path));
            }
            catch (std::filesystem::filesystem_error& error) {
                LOG(LogError) << "FileSystemUtil::getFileSize(): " << error.what();
                return -1;
            }
        }

        std::string expandHomePath(const std::string& path, const bool systemHome)
        {
            // Expand home path if ~ is used.
            if (systemHome)
                return Utils::String::replace(path, "~",
                                              Utils::FileSystem::getSystemHomeDirectory());
            else
                return Utils::String::replace(path, "~", Utils::FileSystem::getHomePath());
        }

        std::string resolveRelativePath(const std::string& path,
                                        const std::string& relativeTo,
                                        const bool allowHome)
        {
            const std::string& genericPath {getGenericPath(path)};
            const std::string& relativeToVar {isDirectory(relativeTo) ? getGenericPath(relativeTo) :
                                                                        getParent(relativeTo)};

            // Nothing to resolve.
            if (!genericPath.length())
                return genericPath;

            // Replace '.' with relativeToVar.
            if ((genericPath[0] == '.') && (genericPath[1] == '/'))
                return (relativeToVar + &(genericPath[1]));

            // Replace '~' with homePath.
            if (allowHome && (genericPath[0] == '~') && (genericPath[1] == '/'))
                return (getHomePath() + &(genericPath[1]));

            // Nothing to resolve.
            return genericPath;
        }

        std::string createRelativePath(const std::string& path,
                                       const std::string& relativeTo,
                                       const bool allowHome)
        {
            bool contains {false};
            std::string relativePath {removeCommonPath(path, relativeTo, contains)};

            if (contains)
                return ("./" + relativePath);

            if (allowHome) {
                relativePath = removeCommonPath(path, getHomePath(), contains);

                if (contains)
                    return ("~/" + relativePath);
            }
            return relativePath;
        }

        std::string removeCommonPath(const std::string& path,
                                     const std::string& commonArg,
                                     bool& contains)
        {
            const std::string& genericPath {getGenericPath(path)};
            const std::string& common {isDirectory(commonArg) ? getGenericPath(commonArg) :
                                                                getParent(commonArg)};

            if (genericPath.find(common) == 0) {
                contains = true;
                return genericPath.substr(common.length() + 1);
            }

            contains = false;
            return genericPath;
        }

        std::string resolveSymlink(const std::string& path)
        {
            const std::string& genericPath {getGenericPath(path)};
            std::string resolved;

            struct stat info;

            // Check if lstat succeeded.
            if (lstat(genericPath.c_str(), &info) == 0) {
                resolved.resize(info.st_size);
                if (readlink(genericPath.c_str(), const_cast<char*>(resolved.data()),
                             resolved.size()) > 0)
                    resolved = getGenericPath(resolved);
            }
            return resolved;
        }

        bool copyFile(const std::string& sourcePath,
                      const std::string& destinationPath,
                      bool overwrite)
        {
            if (!Utils::FileSystem::exists(sourcePath)) {
                LOG(LogError) << "Can't copy file, source file does not exist:";
                LOG(LogError) << sourcePath;
                return true;
            }

            if (isDirectory(destinationPath)) {
                LOG(LogError) << "Destination file is actually a directory:";
                LOG(LogError) << destinationPath;
                return true;
            }

            if (!overwrite && Utils::FileSystem::exists(destinationPath)) {
                LOG(LogError) << "Destination file exists and the overwrite flag "
                                 "has not been set";
                return true;
            }

            std::ifstream sourceFile {sourcePath, std::ios::binary};

            if (sourceFile.fail()) {
                LOG(LogError) << "Couldn't read from source file \"" << sourcePath
                              << "\", permission problems?";
                sourceFile.close();
                return true;
            }

            std::ofstream targetFile {destinationPath, std::ios::binary};

            if (targetFile.fail()) {
                LOG(LogError) << "Couldn't write to target file \"" << destinationPath
                              << "\", permission problems?";
                targetFile.close();
                return true;
            }

            targetFile << sourceFile.rdbuf();

            sourceFile.close();
            targetFile.close();

            return false;
        }

        bool renameFile(const std::string& sourcePath,
                        const std::string& destinationPath,
                        bool overwrite)
        {
            // Don't print any error message for a missing source file as Log will use this
            // function when initializing the logging. It would always generate an error in
            // case it's the first application start (as an old log file would then not exist).
            if (!Utils::FileSystem::exists(sourcePath)) {
                return true;
            }

            if (isDirectory(destinationPath)) {
                LOG(LogError) << "Destination file is actually a directory:";
                LOG(LogError) << destinationPath;
                return true;
            }

            if (!overwrite && Utils::FileSystem::exists(destinationPath)) {
                LOG(LogError) << "Destination file exists and the overwrite flag has not been set";
                return true;
            }

            return std::rename(sourcePath.c_str(), destinationPath.c_str());
        }

        bool createEmptyFile(const std::filesystem::path& path)
        {
            const std::filesystem::path cleanPath {path.lexically_normal().make_preferred()};
            if (Utils::FileSystem::exists(path.string())) {
                LOG(LogError) << "Couldn't create target file \"" << cleanPath.string()
                              << "\" as it already exists";
                return false;
            }
            std::ofstream targetFile {cleanPath, std::ios::binary};
            if (targetFile.fail()) {
                LOG(LogError) << "Couldn't create target file \"" << cleanPath.string()
                              << "\", permission problems?";
                targetFile.close();
                return false;
            }

            targetFile.close();
            return true;
        }

        bool createSymlink(const std::filesystem::path& source, const std::filesystem::path& target)
        {
            try {
                if (std::filesystem::is_directory(source))
                    std::filesystem::create_directory_symlink(source, target);
                else
                    std::filesystem::create_symlink(source, target);
            }
            catch (std::filesystem::filesystem_error& error) {
                LOG(LogError) << "FileSystemUtil::createSymlink(): " << error.what();
                return false;
            }
            return true;
        }

        bool removeFile(const std::string& path)
        {
            const std::string& genericPath {getGenericPath(path)};
            try {
                return std::filesystem::remove(genericPath);
            }
            catch (std::filesystem::filesystem_error& error) {
                LOG(LogError) << "FileSystemUtil::removeFile(): " << error.what();
                return false;
            }
        }

        bool removeDirectory(const std::string& path, bool recursive)
        {
            const std::string& genericPath {getGenericPath(path)};
            try {
                if (recursive)
                    return std::filesystem::remove_all(genericPath);
                else
                    return std::filesystem::remove(genericPath);
            }
            catch (std::filesystem::filesystem_error& error) {
                LOG(LogError) << "FileSystemUtil::removeDirectory(): " << error.what();
                return false;
            }
        }

        bool createDirectory(const std::string& path)
        {
            const std::string& genericPath {getGenericPath(path)};

            if (Utils::FileSystem::exists(genericPath))
                return true;

            if (mkdir(genericPath.c_str(), 0755) == 0)
                return true;

            // Failed to create directory, try to create the parent.
            const std::string& parent {getParent(genericPath)};

            // Only try to create parent if it's not identical to genericPath.
            if (parent != genericPath)
                createDirectory(parent);

                // Try to create directory again now that the parent should exist.

            return (mkdir(genericPath.c_str(), 0755) == 0);
        }

        bool exists(const std::string& path)
        {
            const std::string& genericPath {getGenericPath(path)};
            try {
                return std::filesystem::exists(genericPath);
            }
            catch (std::filesystem::filesystem_error& error) {
                LOG(LogError) << "FileSystemUtil::exists(): " << error.what();
                return false;
            }
        }

        bool driveExists(const std::string& path)
        {
            return false;
        }

        bool isAbsolute(const std::string& path)
        {
            const std::string& genericPath {getGenericPath(path)};
            try {
                return ((genericPath.size() > 0) && (genericPath[0] == '/'));
            }
            catch (...) {
                return false;
            }
        }

        bool isRegularFile(const std::string& path)
        {
            const std::string& genericPath {getGenericPath(path)};
            try {
                return std::filesystem::is_regular_file(genericPath);
            }
            catch (std::filesystem::filesystem_error& error) {
                LOG(LogError) << "FileSystemUtil::isRegularFile(): " << error.what();
                return false;
            }
        }

        bool isDirectory(const std::string& path)
        {
            const std::string& genericPath {getGenericPath(path)};
            try {
                return std::filesystem::is_directory(genericPath);
            }
            catch (std::filesystem::filesystem_error& error) {
                LOG(LogError) << "FileSystemUtil::isDirectory(): " << error.what();
                return false;
            }
        }

        bool isSymlink(const std::string& path)
        {
            const std::string& genericPath {getGenericPath(path)};
            try {
                return std::filesystem::is_symlink(genericPath);
            }
            catch (std::filesystem::filesystem_error& error) {
                LOG(LogError) << "FileSystemUtil::isSymlink(): " << error.what();
                return false;
            }
        }

        bool isHidden(const std::string& path)
        {
            const std::string& genericPath {getGenericPath(path)};

            // Filenames starting with . are hidden in Linux, but
            // we do this check for windows as well.
            if (getFileName(genericPath)[0] == '.')
                return true;

            return false;
        }

    } // namespace FileSystem

} // namespace Utils
