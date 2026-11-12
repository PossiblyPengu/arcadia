//  SPDX-License-Identifier: MIT
//
//  Arcadia
//  GuiToolRunner.h
//
//  Runs one of the setup tools (a script in the deck folder) while showing a busy animation, then shows what
//  it said. Used by the Setup hub.
//

#ifndef ES_APP_GUIS_GUI_TOOL_RUNNER_H
#define ES_APP_GUIS_GUI_TOOL_RUNNER_H

#include "GuiComponent.h"
#include "components/BackgroundComponent.h"
#include "components/BusyComponent.h"
#include "components/ButtonComponent.h"
#include "components/ComponentGrid.h"
#include "components/ImageComponent.h"
#include "components/MenuComponent.h"
#include "components/ScrollableContainer.h"
#include "components/TextComponent.h"

#include <atomic>
#include <functional>
#include <mutex>
#include <thread>

class GuiToolRunner : public GuiComponent
{
public:
    // The command is run through the shell with ARCADIA_OUTPUT=stdout, so the tool prints its message instead of
    // opening a dialog. onClose runs when this screen is closed.
    GuiToolRunner(const std::string& title,
                  const std::string& command,
                  std::function<void()> onClose = nullptr);
    ~GuiToolRunner();

    void update(int deltaTime) override;
    void render(const glm::mat4& parentTrans) override;

    // ARCADIA_OUTPUT=stdout, ARCADIA_HOME and ARCADIA_ROMS, as a prefix for a tool's command.
    static std::string toolEnvironment();
    // Runs a command through sh without Steam's LD_PRELOAD, handing what it prints (both streams) to onOutput as it
    // comes. False if it couldn't be started.
    // exitCode (if given) gets the command's exit status.
    static bool runWithoutPreload(const std::string& cmd,
                                  const std::function<void(const std::string&)>& onOutput,
                                  int* exitCode = nullptr);

private:
    void run();
    void showOutput();
    void onSizeChanged() override;
    bool input(InputConfig* config, Input input) override;
    std::vector<HelpPrompt> getHelpPrompts() override;

    Renderer* mRenderer;
    BackgroundComponent mBackground;
    ComponentGrid mGrid;
    BusyComponent mBusyAnim;
    std::shared_ptr<ComponentGrid> mButtons;
    std::shared_ptr<ButtonComponent> mCloseButton;
    std::shared_ptr<TextComponent> mTitle;
    std::shared_ptr<ImageComponent> mBadge; // when it's done: worked (a tick) or not (an exclamation mark)
    std::atomic<int> mExitCode {0};
    std::shared_ptr<ScrollableContainer> mContainer;
    std::shared_ptr<TextComponent> mBody;

    std::string mCommand;
    std::function<void()> mOnClose;
    std::unique_ptr<std::thread> mThread;
    std::mutex mMutex;
    std::string mOutput;
    std::atomic<bool> mRunning;
    std::atomic<bool> mFinished;
    std::atomic<bool> mChanged {false};
};

#endif // ES_APP_GUIS_GUI_TOOL_RUNNER_H
