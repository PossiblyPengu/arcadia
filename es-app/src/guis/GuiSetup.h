//  SPDX-License-Identifier: MIT
//
//  Arcadia
//  GuiSetup.h
//
//  The Setup screen (DESIGN.md): a checklist of what's ready, with a progress ring, next to a card of setup
//  tools. Each step runs its tool when chosen, and the checklist is read again afterwards. The checklist comes
//  from the get-started tool (get-started.sh --status).
//

#ifndef ES_APP_GUIS_GUI_SETUP_H
#define ES_APP_GUIS_GUI_SETUP_H

#include "GuiComponent.h"
#include "components/BackgroundComponent.h"
#include "components/ComponentList.h"
#include "components/ImageComponent.h"
#include "components/TextComponent.h"

#include <atomic>
#include <mutex>
#include <thread>

class GuiSetup : public GuiComponent
{
public:
    explicit GuiSetup(const std::string& toolsDirectory);
    ~GuiSetup();

    void update(int deltaTime) override;
    void render(const glm::mat4& parentTrans) override;
    bool input(InputConfig* config, Input input) override;
    std::vector<HelpPrompt> getHelpPrompts() override;

private:
    struct Step {
        std::string key;
        bool done;
        std::string label;
        std::string detail;
        std::vector<std::string> code; // what the detail says, as a code and its values (translated here)
    };

    void layout();
    void readStatus();
    void showStatus();
    void runTool(const std::string& title, const std::string& command);
    void openEmulators();
    void setFocusColumn(int column);
    std::shared_ptr<ComponentList> focusedList() { return mColumn == 0 ? mSteps : mTools; }

    Renderer* mRenderer;
    std::string mToolsDirectory;
    int mGameCount {-1}; // games the checklist found last time (-1: not read yet)
    BackgroundComponent mStepsCard;
    BackgroundComponent mToolsCard;
    ImageComponent mRing;
    TextComponent mCount;
    TextComponent mHeadline;
    TextComponent mSubline;
    TextComponent mToolsTitle;
    std::shared_ptr<ComponentList> mSteps;
    std::shared_ptr<ComponentList> mTools;
    int mColumn;

    // What the background status read shares with this screen. The thread holds its own reference, so leaving the
    // screen never waits for it (the read shells out and can take a second or two): a late result is simply dropped.
    struct Shared {
        std::mutex mutex;
        std::vector<Step> status;
        std::atomic<bool> reading {false};
        std::atomic<bool> ready {false};
    };
    std::shared_ptr<Shared> mShared;
};

#endif // ES_APP_GUIS_GUI_SETUP_H
