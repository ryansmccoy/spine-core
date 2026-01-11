import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Layout, Model, TabNode, Action } from 'flexlayout-react';
import type { IJsonModel } from 'flexlayout-react';
import 'flexlayout-react/style/dark.css';
import { TickerInput, PriceChart, OTCVolume, VenueScores, Watchlist } from './widgets';
import { WidgetErrorBoundary } from './components';

// FlexLayout JSON model - defines the docking layout
const layoutJson: IJsonModel = {
  global: {
    tabEnableClose: true,
    tabEnableRename: false,
    tabSetEnableMaximize: true,
    tabSetEnableDrop: true,
    tabSetEnableDrag: true,
    tabSetEnableDivide: true,
    splitterSize: 4,
    splitterExtra: 4,
  },
  borders: [],
  layout: {
    type: 'row',
    weight: 100,
    children: [
      // Left sidebar - Ticker + Watchlist
      {
        type: 'row',
        weight: 20,
        children: [
          {
            type: 'tabset',
            weight: 30,
            children: [
              {
                type: 'tab',
                name: 'Ticker',
                component: 'ticker-input',
                enableClose: false,
              },
            ],
          },
          {
            type: 'tabset',
            weight: 70,
            children: [
              {
                type: 'tab',
                name: 'Watchlist',
                component: 'watchlist',
                enableClose: false,
              },
            ],
          },
        ],
      },
      // Center - Price Chart
      {
        type: 'tabset',
        weight: 55,
        children: [
          {
            type: 'tab',
            name: 'Price Chart',
            component: 'price-chart',
            enableClose: false,
          },
        ],
      },
      // Right panel - OTC + Venues
      {
        type: 'row',
        weight: 25,
        children: [
          {
            type: 'tabset',
            weight: 50,
            children: [
              {
                type: 'tab',
                name: 'OTC Volume',
                component: 'otc-volume',
                enableClose: false,
              },
            ],
          },
          {
            type: 'tabset',
            weight: 50,
            children: [
              {
                type: 'tab',
                name: 'Venue Scores',
                component: 'venue-scores',
                enableClose: false,
              },
            ],
          },
        ],
      },
    ],
  },
};

// Create the model once
const model = Model.fromJson(layoutJson);

function TradingDesktop() {
  // Factory function to render components based on tab type
  const factory = useCallback((node: TabNode) => {
    const component = node.getComponent();
    const name = node.getName();

    const renderWidget = () => {
      switch (component) {
        case 'ticker-input':
          return <TickerInput />;
        case 'watchlist':
          return <Watchlist />;
        case 'price-chart':
          return <PriceChart />;
        case 'otc-volume':
          return <OTCVolume />;
        case 'venue-scores':
          return <VenueScores />;
        default:
          return <div className="p-4">Unknown widget: {component}</div>;
      }
    };

    return (
      <WidgetErrorBoundary widgetName={name}>
        {renderWidget()}
      </WidgetErrorBoundary>
    );
  }, []);

  // Handle layout actions (optional: prevent certain actions)
  const onAction = useCallback((action: Action) => {
    // Allow all actions by default
    return action;
  }, []);

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>Market Spine</h1>
        <span className="header-subtitle">Trading Desktop</span>
        <nav className="admin-links">
          <Link to="/dashboard" className="nav-link" title="Control Plane Dashboard">
            ⚙️ Dashboard
          </Link>
          <a href="http://localhost:8001/docs" target="_blank" rel="noopener noreferrer" title="API Documentation">
            📚 API Docs
          </a>
        </nav>
      </header>
      <div className="layout-container">
        <Layout
          model={model}
          factory={factory}
          onAction={onAction}
        />
      </div>
      <footer className="status-bar">
        <div className="status-item">
          <span className="status-dot status-connected"></span>
          API: localhost:8001
        </div>
        <div className="status-item">
          <span className="status-dot status-connected"></span>
          RabbitMQ: localhost:15672
        </div>
        <div className="status-item">
          <span className="status-dot status-connected"></span>
          Redis: localhost:6379
        </div>
        <div className="status-item status-version">
          v1.0.0-dev
        </div>
      </footer>
    </div>
  );
}

export default TradingDesktop;
