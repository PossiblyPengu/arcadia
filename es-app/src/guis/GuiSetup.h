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

    std::unique_ptr<std::thread> mThread;
    std::mutex mMutex;
    std::vector<Step> mStatus;
    std::atomic<bool> mReading;
    std::atomic<bool> mStatusReady;
};

#endif // ES_APP_GUIS_GUI_SETUP_H
