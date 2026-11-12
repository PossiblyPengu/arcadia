//  SPDX-License-Identifier: MIT
//
//  Arcadia
//  GuiEmulators.h
//
//  The Emulators screen in Setup: every emulator Arcadia can install, the ones your games need first (worked out from
//  your ROM folders and the console list, RetroArch cores included), with what each is for and whether it's ready.
//  A installs one (or updates or removes it), X installs everything your games need. The work is done by
//  deck/lib/emulators.py through deck/tools/install-emulators.sh.
//

#ifndef ES_APP_GUIS_GUI_EMULATORS_H
#define ES_APP_GUIS_GUI_EMULATORS_H

#include "GuiComponent.h"
#include "components/BackgroundComponent.h"
#include "components/ComponentList.h"
#include "components/TextComponent.h"

#include <atomic>
#include <functional>
#include <mutex>
#include <thread>

class GuiEmulators : public GuiComponent
{
public:
    GuiEmulators(const std::string& toolsDirectory, std::function<void()> onClose = nullptr);
    ~GuiEmulators();

    void update(int deltaTime) override;
    void render(const glm::mat4& parentTrans) override;
    bool input(InputConfig* config, Input input) override;
    std::vector<HelpPrompt> getHelpPrompts() override;

private:
    struct Row {
        std::string kind; // "emu", or "none" for a console nothing here installs
        std::string id; // the Flatpak id; for "none", what runs it ("deckhand" or the emulator's name)
        std::string name;
        std::string state; // ready, cores (installed, cores missing) or missing
        bool needed;
        std::string detail;
    };

    void layout();
    void readPlan();
    void showPlan();
    void choose(const Row& row);
    void runTool(const std::string& title, const std::string& args);
    void close();
    int missingNeeded() const;

    Renderer* mRenderer;
    std::string mToolsDirectory;
    std::function<void()> mOnClose;
    BackgroundComponent mCard;
    TextComponent mHeadline;
    TextComponent mSubline;
    std::shared_ptr<ComponentList> mList;

    std::unique_ptr<std::thread> mThread;
    std::mutex mMutex;
    std::vector<Row> mPending;
    std::vector<Row> mRows;
    std::atomic<bool> mReading;
    std::atomic<bool> mPlanReady;
};

#endif // ES_APP_GUIS_GUI_EMULATORS_H
